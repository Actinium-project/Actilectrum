# Electrum - lightweight Bitcoin client
# Copyright (C) 2012 thomasv@ecdsa.org
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import os
import threading
from typing import Optional, Dict

from . import util
from .bitcoin import Hash, hash_encode, int_to_hex, rev_hex
from . import constants
from .util import bfh, bh2u

try:
    import scrypt
    getPoWHash = lambda x: scrypt.hash(x, x, N=1024, r=1, p=1, buflen=32)
except ImportError:
    util.print_msg("Warning: package scrypt not available; synchronization could be very slow")
    from .scrypt import scrypt_1024_1_1_80 as getPoWHash


HEADER_SIZE = 80  # bytes
MAX_TARGET = 0x00000FFFFF000000000000000000000000000000000000000000000000000000


class MissingHeader(Exception):
    pass

class InvalidHeader(Exception):
    pass

def serialize_header(header_dict: dict) -> str:
    s = int_to_hex(header_dict['version'], 4) \
        + rev_hex(header_dict['prev_block_hash']) \
        + rev_hex(header_dict['merkle_root']) \
        + int_to_hex(int(header_dict['timestamp']), 4) \
        + int_to_hex(int(header_dict['bits']), 4) \
        + int_to_hex(int(header_dict['nonce']), 4)
    return s

def deserialize_header(s: bytes, height: int) -> dict:
    if not s:
        raise InvalidHeader('Invalid header: {}'.format(s))
    if len(s) != HEADER_SIZE:
        raise InvalidHeader('Invalid header length: {}'.format(len(s)))
    hex_to_int = lambda s: int('0x' + bh2u(s[::-1]), 16)
    h = {}
    h['version'] = hex_to_int(s[0:4])
    h['prev_block_hash'] = hash_encode(s[4:36])
    h['merkle_root'] = hash_encode(s[36:68])
    h['timestamp'] = hex_to_int(s[68:72])
    h['bits'] = hex_to_int(s[72:76])
    h['nonce'] = hex_to_int(s[76:80])
    h['block_height'] = height
    return h

def hash_header(header: dict) -> str:
    if header is None:
        return '0' * 64
    if header.get('prev_block_hash') is None:
        header['prev_block_hash'] = '00'*32
    return hash_encode(Hash(bfh(serialize_header(header))))

def pow_hash_header(header):
    return hash_encode(getPoWHash(bfh(serialize_header(header))))


blockchains = {}  # type: Dict[int, Blockchain]
blockchains_lock = threading.Lock()


def read_blockchains(config):
    blockchains[0] = Blockchain(config, 0, None)
    fdir = os.path.join(util.get_headers_dir(config), 'forks')
    util.make_dir(fdir)
    l = filter(lambda x: x.startswith('fork_'), os.listdir(fdir))
    l = sorted(l, key = lambda x: int(x.split('_')[1]))
    for filename in l:
        forkpoint = int(filename.split('_')[2])
        parent_id = int(filename.split('_')[1])
        b = Blockchain(config, forkpoint, parent_id)
        h = b.read_header(b.forkpoint)
        if b.parent().can_connect(h, check_height=False):
            blockchains[b.forkpoint] = b
        else:
            util.print_error("cannot connect", filename)
    return blockchains


class Blockchain(util.PrintError):
    """
    Manages blockchain headers and their verification
    """

    def __init__(self, config, forkpoint: int, parent_id: Optional[int]):
        self.config = config
        self.forkpoint = forkpoint
        self.checkpoints = constants.net.CHECKPOINTS
        self.parent_id = parent_id
        assert parent_id != forkpoint
        self.lock = threading.RLock()
        with self.lock:
            self.update_size()

    def with_lock(func):
        def func_wrapper(self, *args, **kwargs):
            with self.lock:
                return func(self, *args, **kwargs)
        return func_wrapper

    def parent(self) -> 'Blockchain':
        return blockchains[self.parent_id]

    def get_max_child(self) -> Optional[int]:
        with blockchains_lock: chains = list(blockchains.values())
        children = list(filter(lambda y: y.parent_id==self.forkpoint, chains))
        return max([x.forkpoint for x in children]) if children else None

    def get_max_forkpoint(self) -> int:
        """Returns the max height where there is a fork
        related to this chain.
        """
        mc = self.get_max_child()
        return mc if mc is not None else self.forkpoint

    def get_branch_size(self) -> int:
        return self.height() - self.get_max_forkpoint() + 1

    def get_name(self) -> str:
        return self.get_hash(self.get_max_forkpoint()).lstrip('00')[0:10]

    def check_header(self, header: dict) -> bool:
        header_hash = hash_header(header)
        height = header.get('block_height')
        return self.check_hash(height, header_hash)

    def check_hash(self, height: int, header_hash: str) -> bool:
        """Returns whether the hash of the block at given height
        is the given hash.
        """
        assert isinstance(header_hash, str) and len(header_hash) == 64, header_hash  # hex
        try:
            return header_hash == self.get_hash(height)
        except Exception:
            return False

    def fork(parent, header: dict) -> 'Blockchain':
        forkpoint = header.get('block_height')
        self = Blockchain(parent.config, forkpoint, parent.forkpoint)
        open(self.path(), 'w+').close()
        self.save_header(header)
        return self

    def height(self) -> int:
        return self.forkpoint + self.size() - 1

    def size(self) -> int:
        with self.lock:
            return self._size

    def update_size(self) -> None:
        p = self.path()
        self._size = os.path.getsize(p)//HEADER_SIZE if os.path.exists(p) else 0

    def verify_header(self, header: dict, prev_hash: str, target: int, expected_header_hash: str=None) -> None:
        _hash = hash_header(header)
        _powhash = pow_hash_header(header)
        if expected_header_hash and expected_header_hash != _hash:
            raise Exception("hash mismatches with expected: {} vs {}".format(expected_header_hash, _hash))
        if prev_hash != header.get('prev_block_hash'):
            raise Exception("prev hash mismatch: %s vs %s" % (prev_hash, header.get('prev_block_hash')))
        if constants.net.TESTNET:
            return
        bits = self.target_to_bits(target)
        if bits != header.get('bits'):
            raise Exception("bits mismatch: %s vs %s" % (bits, header.get('bits')))
        if int('0x' + _powhash, 16) > target:
            raise Exception("insufficient proof of work: %s vs target %s" % (int('0x' + _powhash, 16), target))

    def verify_chunk(self, index: int, data: bytes) -> None:
        num = len(data) // HEADER_SIZE
        start_height = index * 2016
        prev_hash = self.get_hash(start_height - 1)
        target = self.get_target(index-1)
        for i in range(num):
            height = start_height + i
            try:
                expected_header_hash = self.get_hash(height)
            except MissingHeader:
                expected_header_hash = None
            raw_header = data[i*HEADER_SIZE : (i+1)*HEADER_SIZE]
            header = deserialize_header(raw_header, index*2016 + i)
            self.verify_header(header, prev_hash, target, expected_header_hash)
            prev_hash = hash_header(header)

    def path(self):
        d = util.get_headers_dir(self.config)
        if self.parent_id is None:
            filename = 'blockchain_headers'
        else:
            basename = 'fork_%d_%d' % (self.parent_id, self.forkpoint)
            filename = os.path.join('forks', basename)
        return os.path.join(d, filename)

    @with_lock
    def save_chunk(self, index: int, chunk: bytes):
        chunk_within_checkpoint_region = index < len(self.checkpoints)
        # chunks in checkpoint region are the responsibility of the 'main chain'
        if chunk_within_checkpoint_region and self.parent_id is not None:
            main_chain = blockchains[0]
            main_chain.save_chunk(index, chunk)
            return

        delta_height = (index * 2016 - self.forkpoint)
        delta_bytes = delta_height * HEADER_SIZE
        # if this chunk contains our forkpoint, only save the part after forkpoint
        # (the part before is the responsibility of the parent)
        if delta_bytes < 0:
            chunk = chunk[-delta_bytes:]
            delta_bytes = 0
        truncate = not chunk_within_checkpoint_region
        self.write(chunk, delta_bytes, truncate)
        self.swap_with_parent()

    @with_lock
    def swap_with_parent(self) -> None:
        if self.parent_id is None:
            return
        parent_branch_size = self.parent().height() - self.forkpoint + 1
        if parent_branch_size >= self.size():
            return
        self.print_error("swap", self.forkpoint, self.parent_id)
        parent_id = self.parent_id
        forkpoint = self.forkpoint
        parent = self.parent()
        self.assert_headers_file_available(self.path())
        with open(self.path(), 'rb') as f:
            my_data = f.read()
        self.assert_headers_file_available(parent.path())
        with open(parent.path(), 'rb') as f:
            f.seek((forkpoint - parent.forkpoint)*HEADER_SIZE)
            parent_data = f.read(parent_branch_size*HEADER_SIZE)
        self.write(parent_data, 0)
        parent.write(my_data, (forkpoint - parent.forkpoint)*HEADER_SIZE)
        # store file path
        with blockchains_lock: chains = list(blockchains.values())
        for b in chains:
            b.old_path = b.path()
        # swap parameters
        self.parent_id = parent.parent_id; parent.parent_id = parent_id
        self.forkpoint = parent.forkpoint; parent.forkpoint = forkpoint
        self._size = parent._size; parent._size = parent_branch_size
        # move files
        for b in chains:
            if b in [self, parent]: continue
            if b.old_path != b.path():
                self.print_error("renaming", b.old_path, b.path())
                os.rename(b.old_path, b.path())
        # update pointers
        with blockchains_lock:
            blockchains[self.forkpoint] = self
            blockchains[parent.forkpoint] = parent

    def assert_headers_file_available(self, path):
        if os.path.exists(path):
            return
        elif not os.path.exists(util.get_headers_dir(self.config)):
            raise FileNotFoundError('Electrum headers_dir does not exist. Was it deleted while running?')
        else:
            raise FileNotFoundError('Cannot find headers file but headers_dir is there. Should be at {}'.format(path))

    def write(self, data: bytes, offset: int, truncate: bool=True) -> None:
        filename = self.path()
        with self.lock:
            self.assert_headers_file_available(filename)
            with open(filename, 'rb+') as f:
                if truncate and offset != self._size * HEADER_SIZE:
                    f.seek(offset)
                    f.truncate()
                f.seek(offset)
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            self.update_size()

    @with_lock
    def save_header(self, header: dict) -> None:
        delta = header.get('block_height') - self.forkpoint
        data = bfh(serialize_header(header))
        # headers are only _appended_ to the end:
        assert delta == self.size()
        assert len(data) == HEADER_SIZE
        self.write(data, delta*HEADER_SIZE)
        self.swap_with_parent()

    def read_header(self, height: int) -> Optional[dict]:
        assert self.parent_id != self.forkpoint
        if height < 0:
            return
        if height < self.forkpoint:
            return self.parent().read_header(height)
        if height > self.height():
            return
        delta = height - self.forkpoint
        name = self.path()
        self.assert_headers_file_available(name)
        with open(name, 'rb') as f:
            f.seek(delta * HEADER_SIZE)
            h = f.read(HEADER_SIZE)
            if len(h) < HEADER_SIZE:
                raise Exception('Expected to read a full header. This was only {} bytes'.format(len(h)))
        if h == bytes([0])*HEADER_SIZE:
            return None
        return deserialize_header(h, height)

    def get_hash(self, height: int) -> str:
        def is_height_checkpoint():
            within_cp_range = height <= constants.net.max_checkpoint()
            at_chunk_boundary = (height+1) % 2016 == 0
            return within_cp_range and at_chunk_boundary

        if height == -1:
            return '0000000000000000000000000000000000000000000000000000000000000000'
        elif height == 0:
            return constants.net.GENESIS
        elif is_height_checkpoint():
            index = height // 2016
            h, t, _ = self.checkpoints[index]
            return h
        else:
            header = self.read_header(height)
            if header is None:
                raise MissingHeader(height)
            return hash_header(header)

    def get_timestamp(self, height):
        if height < len(self.checkpoints) * 2016 and (height+1) % 2016 == 0:
            index = height // 2016
            _, _, ts = self.checkpoints[index]
            return ts
        return self.read_header(height).get('timestamp')

    def get_target(self, index: int) -> int:
        # compute target from chunk x, used in chunk x+1
        if constants.net.TESTNET:
            return 0
        if index == -1:
            return 0x00000FFFF0000000000000000000000000000000000000000000000000000000
        if index < len(self.checkpoints):
            h, t, _ = self.checkpoints[index]
            return t
        # new target
        # Litecoin: go back the full period unless it's the first retarget
        first_timestamp = self.get_timestamp(index * 2016 - 1 if index > 0 else 0)
        last = self.read_header(index * 2016 + 2015)
        if not first_timestamp or not last:
            raise MissingHeader()
        bits = last.get('bits')
        target = self.bits_to_target(bits)
        nActualTimespan = last.get('timestamp') - first_timestamp
        nTargetTimespan = 84 * 60 * 60
        nActualTimespan = max(nActualTimespan, nTargetTimespan // 4)
        nActualTimespan = min(nActualTimespan, nTargetTimespan * 4)
        new_target = min(MAX_TARGET, (target * nActualTimespan) // nTargetTimespan)
        return new_target

    def bits_to_target(self, bits: int) -> int:
        bitsN = (bits >> 24) & 0xff
        if not (bitsN >= 0x03 and bitsN <= 0x1e):
            raise Exception("First part of bits should be in [0x03, 0x1e]")
        bitsBase = bits & 0xffffff
        if not (bitsBase >= 0x8000 and bitsBase <= 0x7fffff):
            raise Exception("Second part of bits should be in [0x8000, 0x7fffff]")
        return bitsBase << (8 * (bitsN-3))

    def target_to_bits(self, target: int) -> int:
        c = ("%064x" % target)[2:]
        while c[:2] == '00' and len(c) > 6:
            c = c[2:]
        bitsN, bitsBase = len(c) // 2, int('0x' + c[:6], 16)
        if bitsBase >= 0x800000:
            bitsN += 1
            bitsBase >>= 8
        return bitsN << 24 | bitsBase

    def can_connect(self, header: dict, check_height: bool=True) -> bool:
        if header is None:
            return False
        height = header['block_height']
        if check_height and self.height() != height - 1:
            #self.print_error("cannot connect at height", height)
            return False
        if height == 0:
            return hash_header(header) == constants.net.GENESIS
        try:
            prev_hash = self.get_hash(height - 1)
        except:
            return False
        if prev_hash != header.get('prev_block_hash'):
            return False
        try:
            target = self.get_target(height // 2016 - 1)
        except MissingHeader:
            return False
        try:
            self.verify_header(header, prev_hash, target)
        except BaseException as e:
            return False
        return True

    def connect_chunk(self, idx: int, hexdata: str) -> bool:
        try:
            data = bfh(hexdata)
            self.verify_chunk(idx, data)
            #self.print_error("validated chunk %d" % idx)
            self.save_chunk(idx, data)
            return True
        except BaseException as e:
            self.print_error('verify_chunk %d failed'%idx, str(e))
            return False

    def get_checkpoints(self):
        # for each chunk, store the hash of the last block and the target after the chunk
        cp = []
        n = self.height() // 2016
        for index in range(n):
            h = self.get_hash((index+1) * 2016 -1)
            target = self.get_target(index)
            # Litecoin: also store the timestamp of the last block
            tstamp = self.get_timestamp((index+1) * 2016 - 1)
            cp.append((h, target, tstamp))
        return cp


def check_header(header: dict) -> Optional[Blockchain]:
    if type(header) is not dict:
        return None
    with blockchains_lock: chains = list(blockchains.values())
    for b in chains:
        if b.check_header(header):
            return b
    return None


def can_connect(header: dict) -> Optional[Blockchain]:
    with blockchains_lock: chains = list(blockchains.values())
    for b in chains:
        if b.can_connect(header):
            return b
    return None

from cpython.pycapsule cimport PyCapsule_GetPointer
from libc.stdint cimport uint32_t, uint64_t
from numpy.random cimport bitgen_t

cdef extern from *:
    int __builtin_popcountll(unsigned long long value) noexcept nogil


def draw(generator, int n, unsigned long long limit):
    if n < 3 or n > 128 or limit == 0:
        raise ValueError((n, limit))
    cdef bitgen_t *engine = <bitgen_t *>PyCapsule_GetPointer(generator.capsule, "BitGenerator")
    cdef uint32_t bound = (n - 1) * (n - 2)
    cdef uint32_t threshold = (<uint64_t>1 << 32) % bound
    cdef uint32_t value, choice
    cdef uint64_t seen[2]
    cdef int rows[128][2]
    cdef int i, a, b, occupied
    cdef unsigned long long proposal
    cdef bint candidate = False
    with generator.lock:
        with nogil:
            for proposal in range(limit):
                seen[0] = 0
                seen[1] = 0
                for i in range(n):
                    value = engine.next_uint32(engine.state)
                    while value < threshold:
                        value = engine.next_uint32(engine.state)
                    if n == 128:
                        choice = value % 16002
                        a = choice // 126
                        b = choice % 126
                    else:
                        choice = value % bound
                        a = choice // (n - 2)
                        b = choice % (n - 2)
                    b += b >= a
                    a += a >= i
                    b += b >= i
                    rows[i][0] = a
                    rows[i][1] = b
                    seen[a >> 6] |= <uint64_t>1 << (a & 63)
                    seen[b >> 6] |= <uint64_t>1 << (b & 63)
                occupied = __builtin_popcountll(seen[0]) + __builtin_popcountll(seen[1])
                if occupied >= n - 1:
                    candidate = True
                    break
    return int(proposal + 1), [[rows[i][0], rows[i][1]] for i in range(n)] if candidate else None

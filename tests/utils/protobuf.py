def encode_varint(value):
    result = bytearray()

    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7

    result.append(value)
    return bytes(result)


def field_key(field_number, wire_type):
    return encode_varint((field_number << 3) | wire_type)


def bytes_field(field_number, value):
    if not value:
        return b""

    return field_key(field_number, 2) + encode_varint(len(value)) + value


def string_field(field_number, value):
    if not value:
        return b""

    return bytes_field(field_number, value.encode("utf-8"))


def uint64_field(field_number, value):
    if value == 0:
        return b""

    return field_key(field_number, 0) + encode_varint(value)
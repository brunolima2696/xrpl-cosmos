from utils.protobuf import *

def make_any(type_url, value):
    return (
        string_field(1, type_url)
        + bytes_field(2, value)
    )


def make_coin(denom, amount):
    return (
        string_field(1, denom)
        + string_field(2, str(amount))
    )

def make_height(revision_number, revision_height):
    return (
        uint64_field(1, revision_number)
        + uint64_field(2, revision_height)
    )

def make_msg_send(from_address, to_address, amount, denom):
    coin = make_coin(denom, amount)

    return (
        string_field(1, from_address)
        + string_field(2, to_address)
        + bytes_field(3, coin)
    )

def make_msg_transfer(
    source_port,
    source_channel,
    sender,
    receiver,
    amount,
    denom,
    timeout_timestamp,
    memo="",
):
    token = make_coin(denom, amount)
    timeout_height = make_height(0, 0)

    return (
        string_field(1, source_port)
        + string_field(2, source_channel)
        + bytes_field(3, token)
        + string_field(4, sender)
        + string_field(5, receiver)
        + bytes_field(6, timeout_height)
        + uint64_field(7, timeout_timestamp)
        + string_field(8, memo)
    )

def make_pubkey(pubkey_compressed):
    return bytes_field(1, pubkey_compressed)


def make_tx_body(msg_any, memo=""):
    return (
        bytes_field(1, msg_any)
        + string_field(2, memo)
    )


def make_mode_info_direct():
    # SignMode.SIGN_MODE_DIRECT = 1
    single = uint64_field(1, 1)

    return bytes_field(1, single)


def make_signer_info(pubkey_any, sequence):
    mode_info = make_mode_info_direct()

    return (
        bytes_field(1, pubkey_any)
        + bytes_field(2, mode_info)
        + uint64_field(3, sequence)
    )


def make_fee(amount, denom, gas_limit):
    fee_coin = make_coin(denom, amount)

    return (
        bytes_field(1, fee_coin)
        + uint64_field(2, gas_limit)
    )


def make_auth_info(signer_info, fee):
    return (
        bytes_field(1, signer_info)
        + bytes_field(2, fee)
    )


def make_sign_doc(body_bytes, auth_info_bytes, chain_id, account_number):
    return (
        bytes_field(1, body_bytes)
        + bytes_field(2, auth_info_bytes)
        + string_field(3, chain_id)
        + uint64_field(4, account_number)
    )


def make_tx_raw(body_bytes, auth_info_bytes, signature):
    return (
        bytes_field(1, body_bytes)
        + bytes_field(2, auth_info_bytes)
        + bytes_field(3, signature)
    )
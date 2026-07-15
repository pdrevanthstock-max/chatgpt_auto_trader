from concurrent.futures import ThreadPoolExecutor

from application.position_reservation import PositionReservation


def test_only_one_simultaneous_candidate_can_reserve_global_position():
    reservation = PositionReservation()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reservation.try_reserve, [f"candidate-{i}" for i in range(20)]))

    assert sum(result is not None for result in results) == 1
    assert reservation.snapshot().state == "RESERVED"


def test_reservation_requires_owner_token_for_activate_and_release():
    reservation = PositionReservation()
    token = reservation.try_reserve("candidate-a")

    assert token is not None
    assert reservation.activate("wrong") is False
    assert reservation.release("wrong") is False
    assert reservation.activate(token) is True
    assert reservation.snapshot().state == "ACTIVE"
    assert reservation.release(token) is True
    assert reservation.snapshot().state == "EMPTY"

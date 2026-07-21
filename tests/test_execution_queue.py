from threading import Event

from core.enums import SignalType
from core.models import ExecutionSignal
from execution.execution_queue import ExecutionQueue


def test_background_failure_is_reported_with_the_signal_and_queue_keeps_running():
    queue = ExecutionQueue()
    failed = Event()
    processed = Event()
    failures = []

    def execute(signal):
        if signal.reason == "fail":
            raise RuntimeError("paper limit was not filled")
        processed.set()

    def on_error(signal, error):
        failures.append((signal, error))
        failed.set()

    queue.start_background_worker(execute, on_error=on_error)
    queue.enqueue(ExecutionSignal(type=SignalType.ENTRY, reason="fail"))
    assert failed.wait(2.0)
    queue.enqueue(ExecutionSignal(type=SignalType.ENTRY, reason="continue"))
    assert processed.wait(2.0)
    queue.stop_background_worker()

    assert failures[0][0].reason == "fail"
    assert str(failures[0][1]) == "paper limit was not filled"

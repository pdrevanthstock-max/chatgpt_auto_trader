import queue
import logging
import threading
import time
from typing import Optional, Callable
from core.models import ExecutionSignal

logger = logging.getLogger("AutoTrader")

class ExecutionQueue:
    """
    Thread-safe FIFO queue to serialize trade actions
    (Entry, Exit, Rotation, HedgeCut) and prevent race conditions.
    """
    def __init__(self) -> None:
        self._queue: queue.Queue[ExecutionSignal] = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def enqueue(self, signal: ExecutionSignal) -> None:
        self._queue.put(signal)
        logger.info(f"ExecutionQueue: Enqueued signal {signal.type.value}")

    def clear(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def process_pending_sync(
        self,
        executor_callback: Callable[[ExecutionSignal], None],
        on_error: Optional[Callable[[ExecutionSignal, Exception], None]] = None,
    ) -> None:
        """Processes all currently pending signals synchronously (useful for backtesting)."""
        while not self._queue.empty():
            try:
                signal = self._queue.get_nowait()
                logger.info(f"ExecutionQueue [SYNC]: Processing signal {signal.type.value}")
                executor_callback(signal)
                self._queue.task_done()
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"Error processing sync queue signal: {e}")
                if on_error is not None:
                    on_error(signal, e)
                self._queue.task_done()

    def start_background_worker(
        self,
        executor_callback: Callable[[ExecutionSignal], None],
        on_error: Optional[Callable[[ExecutionSignal, Exception], None]] = None,
    ) -> None:
        """Starts a background thread to process signals in live/paper trading."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker_loop,
            args=(executor_callback, on_error),
            daemon=True
        )
        self._thread.start()
        logger.info("ExecutionQueue: Background worker thread started.")

    def stop_background_worker(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("ExecutionQueue: Background worker thread stopped.")

    def _worker_loop(
        self,
        executor_callback: Callable[[ExecutionSignal], None],
        on_error: Optional[Callable[[ExecutionSignal, Exception], None]],
    ) -> None:
        while self._running:
            try:
                # Block for up to 1 second waiting for a signal
                signal = self._queue.get(timeout=1.0)
                logger.info(f"ExecutionQueue [ASYNC]: Dequeued signal {signal.type.value}")
                
                # Execute the signal handler
                try:
                    executor_callback(signal)
                except Exception as exc:
                    logger.error(f"Error executing queued signal: {exc}")
                    if on_error is not None:
                        on_error(signal, exc)
                finally:
                    self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in ExecutionQueue worker loop: {e}")
                time.sleep(1.0)

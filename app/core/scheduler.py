
# scheduler.py
# app.core.scheduler

import threading
import time
import heapq
from dataclasses import dataclass, field
from typing import Callable, Any, List, Optional, Tuple

from app.core.logger import logger


@dataclass(order=True)
class ScheduledTask:
    """Запланированная задача"""
    run_at: float
    priority: int
    action: Callable = field(compare=False)
    args: Tuple[Any, ...] = field(default_factory=tuple, compare=False)
    kwargs: dict = field(default_factory=dict, compare=False)
    interval: Optional[float] = field(default=None, compare=False)  # None = одноразовая
    cancelled: bool = field(default=False, compare=False)
    name: str = field(default="", compare=False)


class EventScheduler:
    """
    Планировщик событий на основе heap.
    
    Поддерживает:
    - Одноразовые задачи (schedule_in, schedule_at)
    - Периодические задачи (schedule_every)
    - Отмену задач (cancel)
    - Работу в отдельном потоке
    """
    
    def __init__(self) -> None:
        self._tasks: List[ScheduledTask] = []
        self._lock = threading.Lock()
        self._new_task_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._counter = 0  # для приоритета в heapq

    # ════════════════════════════════════════════════════════════════
    # ПУБЛИЧНЫЙ API
    # ════════════════════════════════════════════════════════════════

    def start(self) -> None:
        """Запустить планировщик в отдельном потоке"""
        if self._thread and self._thread.is_alive():
            logger.warning("EventScheduler already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="EventSchedulerThread",
            daemon=True,
        )
        self._thread.start()
        logger.debug("EventScheduler started")

    def stop(self) -> None:
        """Остановить планировщик"""
        self._stop_event.set()
        self._new_task_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.debug("EventScheduler stopped")

    def is_running(self) -> bool:
        """Проверить работает ли планировщик"""
        return self._thread is not None and self._thread.is_alive()

    def schedule_at(
        self,
        timestamp: float,
        func: Callable,
        *args: Any,
        interval: Optional[float] = None,
        name: str = "",
        **kwargs: Any,
    ) -> ScheduledTask:
        """
        Запланировать задачу на конкретное время.
        
        Args:
            timestamp: Unix timestamp когда выполнить
            func: Функция для выполнения
            interval: Если не None - повторять каждые N секунд
            name: Имя задачи для логирования
        """
        with self._lock:
            self._counter += 1
            task = ScheduledTask(
                run_at=timestamp,
                priority=self._counter,
                action=func,
                args=args,
                kwargs=kwargs,
                interval=interval,
                name=name or func.__name__,
            )
            heapq.heappush(self._tasks, task)
            self._new_task_event.set()
        
        logger.debug(f"Scheduled task '{task.name}' at {timestamp} (interval={interval})")
        return task

    def schedule_in(
        self,
        delay: float,
        func: Callable,
        *args: Any,
        name: str = "",
        **kwargs: Any,
    ) -> ScheduledTask:
        """Запланировать одноразовую задачу через delay секунд"""
        return self.schedule_at(
            time.time() + delay, 
            func, 
            *args, 
            interval=None, 
            name=name,
            **kwargs
        )

    def schedule_every(
        self,
        interval: float,
        func: Callable,
        *args: Any,
        delay_first: Optional[float] = None,
        name: str = "",
        **kwargs: Any,
    ) -> ScheduledTask:
        """
        Запланировать периодическую задачу.
        
        Args:
            interval: Период в секундах
            func: Функция для выполнения
            delay_first: Задержка перед первым запуском (по умолчанию = interval)
            name: Имя задачи
        """
        if delay_first is None:
            delay_first = interval
            
        return self.schedule_at(
            time.time() + delay_first,
            func,
            *args,
            interval=interval,
            name=name,
            **kwargs,
        )

    def cancel(self, task: ScheduledTask) -> None:
        """Отменить задачу (ленивая отмена)"""
        with self._lock:
            task.cancelled = True
        logger.debug(f"Task '{task.name}' cancelled")

    def cancel_all(self) -> None:
        """Отменить все задачи"""
        with self._lock:
            for task in self._tasks:
                task.cancelled = True
            self._tasks.clear()
        logger.info("All tasks cancelled")

    def get_pending_count(self) -> int:
        """Получить количество ожидающих задач"""
        with self._lock:
            return len([t for t in self._tasks if not t.cancelled])

    # ════════════════════════════════════════════════════════════════
    # ВНУТРЕННИЙ ЦИКЛ
    # ════════════════════════════════════════════════════════════════

    def _run_loop(self) -> None:
        """Главный цикл планировщика"""
        logger.debug("EventScheduler loop started")

        while not self._stop_event.is_set():
            try:
                with self._lock:
                    if not self._tasks:
                        next_run_at = None
                    else:
                        next_task = self._tasks[0]
                        next_run_at = next_task.run_at

                if next_run_at is None:
                    # Нет задач - ждём появления новой
                    self._new_task_event.wait(timeout=1.0)
                    self._new_task_event.clear()
                    continue

                now = time.time()
                wait_for = next_run_at - now

                if wait_for > 0:
                    # Ждём до ближайшей задачи или до добавления новой
                    triggered = self._new_task_event.wait(timeout=wait_for)
                    if triggered:
                        self._new_task_event.clear()
                    continue

                # Достигли времени выполнения - достаём задачу
                with self._lock:
                    if not self._tasks:
                        continue
                    task = heapq.heappop(self._tasks)

                if task.cancelled:
                    continue

                # Выполняем задачу
                try:
                    logger.debug(f"Running task: {task.name}")
                    task.action(*task.args, **task.kwargs)
                except Exception as exc:
                    logger.exception(f"❌ Error in task '{task.name}': {exc}")

                # Если периодическая - перепланируем
                if task.interval and not task.cancelled:
                    task.run_at = time.time() + task.interval
                    with self._lock:
                        heapq.heappush(self._tasks, task)

            except Exception as exc:
                logger.exception(f"Unexpected error in EventScheduler loop: {exc}")
                time.sleep(1.0)

        logger.debug("EventScheduler loop exited")

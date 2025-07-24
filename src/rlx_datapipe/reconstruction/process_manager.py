"""Process Manager for multi-symbol pipeline orchestration.

This module implements the ProcessManager class which handles:
- Worker process lifecycle management
- Health monitoring and automatic restarts
- Resource allocation and monitoring
- Graceful shutdown coordination
"""

import multiprocessing
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from multiprocessing import Process, Queue
from typing import Any, Optional

import psutil
from loguru import logger

from .config import MultiSymbolConfig, SymbolConfig


class WorkerState(Enum):
    """Worker process lifecycle states."""
    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    CRASHED = "crashed"
    RESTARTING = "restarting"


@dataclass
class WorkerHealth:
    """Health metrics for a worker process."""
    process: Process
    state: WorkerState
    last_heartbeat: float
    messages_processed: int = 0
    errors_count: int = 0
    restart_count: int = 0
    memory_usage: float = 0.0
    cpu_percent: float = 0.0


@dataclass
class WorkerInfo:
    """Complete information about a worker."""
    symbol: str
    config: SymbolConfig
    queue: Queue
    health: WorkerHealth
    process_id: int | None = None


class ProcessManager:
    """Manages multiple worker processes for multi-symbol processing."""

    def __init__(self, config: MultiSymbolConfig, worker_target: Callable, output_dir: str):
        """Initialize the process manager.
        
        Args:
            config: Multi-symbol configuration
            worker_target: Function to run in each worker process
            output_dir: Base output directory for all workers
        """
        self.config = config
        self.worker_target = worker_target
        self.output_dir = output_dir
        self.workers: dict[str, WorkerInfo] = {}
        self.running = False
        self.shutdown_event = multiprocessing.Event()
        self._health_monitor_process: Process | None = None

    def start_worker(self, symbol: str, symbol_config: SymbolConfig) -> None:
        """Start a new worker process for a symbol.
        
        Args:
            symbol: Symbol identifier (e.g., 'BTC-USDT')
            symbol_config: Configuration for this symbol
        """
        if symbol in self.workers:
            logger.warning(f"Worker for {symbol} already exists")
            return

        # Create communication queue
        queue = Queue(maxsize=symbol_config.queue_size)

        # Create worker process
        process = Process(
            target=self._worker_wrapper,
            args=(symbol, queue, symbol_config, self.shutdown_event, self.output_dir),
            name=f"Worker-{symbol}"
        )

        # Create health tracking
        health = WorkerHealth(
            process=process,
            state=WorkerState.INITIALIZING,
            last_heartbeat=time.time()
        )

        # Store worker info
        self.workers[symbol] = WorkerInfo(
            symbol=symbol,
            config=symbol_config,
            queue=queue,
            health=health
        )

        # Start the process
        process.start()
        self.workers[symbol].process_id = process.pid

        # Set CPU affinity if configured
        if symbol_config.cpu_affinity and process.pid:
            self._set_cpu_affinity(process.pid, symbol_config.cpu_affinity)

        logger.info(f"Started worker for {symbol} with PID {process.pid}")

    def _worker_wrapper(self, symbol: str, queue: Queue, config: SymbolConfig,
                       shutdown_event: multiprocessing.Event, output_dir: str) -> None:
        """Wrapper function that runs in the worker process.
        
        Args:
            symbol: Symbol identifier
            queue: Input queue for messages
            config: Symbol configuration
            shutdown_event: Event signaling shutdown
            output_dir: Base output directory
        """
        # Set resource limits
        if config.memory_limit_mb:
            self._set_memory_limit(config.memory_limit_mb)

        # Run the actual worker function
        try:
            self.worker_target(symbol, queue, config, shutdown_event, output_dir)
        except Exception as e:
            logger.error(f"Worker {symbol} crashed: {e}")
            raise

    def _set_cpu_affinity(self, pid: int, cpus: list[int]) -> None:
        """Set CPU affinity for a process.
        
        Args:
            pid: Process ID
            cpus: List of CPU cores to bind to
        """
        try:
            if hasattr(os, "sched_setaffinity"):
                os.sched_setaffinity(pid, cpus)
                logger.debug(f"Set CPU affinity for PID {pid} to CPUs {cpus}")
        except Exception as e:
            logger.warning(f"Failed to set CPU affinity: {e}")

    def _set_memory_limit(self, limit_mb: int) -> None:
        """Set memory limit for current process.
        
        Args:
            limit_mb: Memory limit in megabytes
        """
        try:
            import resource
            limit_bytes = limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
            logger.debug(f"Set memory limit to {limit_mb}MB")
        except Exception as e:
            logger.warning(f"Failed to set memory limit: {e}")

    def start_all_workers(self) -> None:
        """Start workers for all configured symbols."""
        for symbol_config in self.config.symbols:
            if symbol_config.enabled:
                self.start_worker(symbol_config.name, symbol_config)

    def stop_worker(self, symbol: str, timeout: float = 30.0) -> None:
        """Stop a worker process gracefully.
        
        Args:
            symbol: Symbol identifier
            timeout: Seconds to wait for graceful shutdown
        """
        if symbol not in self.workers:
            logger.warning(f"No worker found for {symbol}")
            return

        worker = self.workers[symbol]
        worker.health.state = WorkerState.STOPPING

        # Send shutdown signal via queue
        try:
            worker.queue.put_nowait(None)
        except:
            pass

        # Wait for process to finish
        worker.health.process.join(timeout=timeout)

        # Force terminate if still running
        if worker.health.process.is_alive():
            logger.warning(f"Force terminating worker {symbol}")
            worker.health.process.terminate()
            worker.health.process.join(timeout=5.0)

        worker.health.state = WorkerState.STOPPED
        logger.info(f"Stopped worker for {symbol}")

    def stop_all_workers(self) -> None:
        """Stop all worker processes."""
        logger.info("Stopping all workers...")

        # Signal shutdown to all workers
        self.shutdown_event.set()

        # Stop each worker
        for symbol in list(self.workers.keys()):
            self.stop_worker(symbol, timeout=self.config.process_manager.shutdown_timeout_seconds)

        self.workers.clear()

    def restart_worker(self, symbol: str) -> None:
        """Restart a crashed worker.
        
        Args:
            symbol: Symbol identifier
        """
        if symbol not in self.workers:
            logger.error(f"Cannot restart unknown worker {symbol}")
            return

        worker = self.workers[symbol]
        worker.health.restart_count += 1

        # Check restart limit
        if worker.health.restart_count > self.config.process_manager.max_restart_attempts:
            logger.error(f"Worker {symbol} exceeded max restart attempts")
            worker.health.state = WorkerState.STOPPED
            return

        logger.info(f"Restarting worker {symbol} (attempt {worker.health.restart_count})")
        worker.health.state = WorkerState.RESTARTING

        # Stop the old process
        self.stop_worker(symbol, timeout=5.0)

        # Wait before restarting
        time.sleep(self.config.process_manager.restart_delay_seconds)

        # Start new worker
        self.start_worker(symbol, worker.config)

    def start_health_monitor(self) -> None:
        """Start the health monitoring process."""
        if self._health_monitor_process and self._health_monitor_process.is_alive():
            logger.warning("Health monitor already running")
            return

        self._health_monitor_process = Process(
            target=self._health_monitor_loop,
            name="HealthMonitor"
        )
        self._health_monitor_process.start()
        logger.info("Started health monitor")

    def _health_monitor_loop(self) -> None:
        """Health monitoring loop (runs in separate process)."""
        while not self.shutdown_event.is_set():
            try:
                self._check_worker_health()
                time.sleep(self.config.process_manager.health_check_interval_seconds)
            except Exception as e:
                logger.error(f"Health monitor error: {e}")

    def _check_worker_health(self) -> None:
        """Check health of all workers."""
        current_time = time.time()

        for symbol, worker in list(self.workers.items()):
            # Check if process is alive
            if not worker.health.process.is_alive():
                if worker.health.state == WorkerState.RUNNING:
                    logger.error(f"Worker {symbol} crashed")
                    worker.health.state = WorkerState.CRASHED
                    self.restart_worker(symbol)
                continue

            # Check process metrics
            try:
                if worker.process_id:
                    proc = psutil.Process(worker.process_id)
                    worker.health.memory_usage = proc.memory_info().rss / 1024 / 1024  # MB
                    worker.health.cpu_percent = proc.cpu_percent(interval=0.1)
            except psutil.NoSuchProcess:
                logger.warning(f"Cannot find process for worker {symbol}")

            # Update state
            if worker.health.state == WorkerState.INITIALIZING:
                # Give workers time to initialize
                if current_time - worker.health.last_heartbeat > 10:
                    worker.health.state = WorkerState.RUNNING

    def get_worker_queue(self, symbol: str) -> Optional[Queue]:
        """Get the input queue for a worker.
        
        Args:
            symbol: Symbol identifier
            
        Returns:
            Queue for the worker, or None if not found
        """
        worker = self.workers.get(symbol)
        return worker.queue if worker else None

    def get_worker_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all workers.
        
        Returns:
            Dictionary of worker statistics by symbol
        """
        stats = {}
        for symbol, worker in self.workers.items():
            stats[symbol] = {
                "state": worker.health.state.value,
                "messages_processed": worker.health.messages_processed,
                "errors_count": worker.health.errors_count,
                "restart_count": worker.health.restart_count,
                "memory_mb": worker.health.memory_usage,
                "cpu_percent": worker.health.cpu_percent,
                "process_id": worker.process_id
            }
        return stats

    def start(self) -> None:
        """Start the process manager and all configured workers."""
        logger.info("Starting process manager...")
        self.running = True
        self.shutdown_event.clear()

        # Start all workers
        self.start_all_workers()

        # Start health monitoring
        self.start_health_monitor()

        logger.info("Process manager started")

    def stop(self) -> None:
        """Stop the process manager and all workers."""
        logger.info("Stopping process manager...")
        self.running = False

        # Stop all workers
        self.stop_all_workers()

        # Stop health monitor
        if self._health_monitor_process and self._health_monitor_process.is_alive():
            self.shutdown_event.set()
            self._health_monitor_process.join(timeout=5.0)
            if self._health_monitor_process.is_alive():
                self._health_monitor_process.terminate()

        logger.info("Process manager stopped")

    def add_symbol(self, symbol: str, config: SymbolConfig) -> None:
        """Dynamically add a new symbol for processing.
        
        Args:
            symbol: Symbol identifier
            config: Symbol configuration
        """
        if symbol in self.workers:
            logger.warning(f"Symbol {symbol} already being processed")
            return

        logger.info(f"Adding new symbol: {symbol}")
        self.start_worker(symbol, config)

    def remove_symbol(self, symbol: str) -> None:
        """Dynamically remove a symbol from processing.
        
        Args:
            symbol: Symbol identifier
        """
        if symbol not in self.workers:
            logger.warning(f"Symbol {symbol} not being processed")
            return

        logger.info(f"Removing symbol: {symbol}")
        self.stop_worker(symbol)
        del self.workers[symbol]


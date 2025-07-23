"""Memory-mapped file processing for efficient I/O operations."""

import gc
import mmap
import os
from pathlib import Path
from typing import Generator, Optional, Tuple

import numpy as np
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger


class MemoryMappedProcessor:
    """Processor for memory-mapped file operations."""
    
    def __init__(
        self,
        chunk_size: int = 100_000,
        max_memory_mb: int = 1024,
        gc_interval: int = 10,
    ):
        """
        Initialize memory-mapped processor.
        
        Args:
            chunk_size: Number of rows per chunk
            max_memory_mb: Maximum memory usage in MB
            gc_interval: Number of chunks between GC calls
        """
        self.chunk_size = chunk_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.gc_interval = gc_interval
        self.chunks_processed = 0
        
        logger.info(
            f"MemoryMappedProcessor initialized with chunk_size={chunk_size}, "
            f"max_memory={max_memory_mb}MB"
        )
    
    def read_parquet_mmap(
        self,
        file_path: Path,
        columns: Optional[list[str]] = None,
    ) -> Generator[pl.DataFrame, None, None]:
        """
        Read Parquet file using memory mapping.
        
        Args:
            file_path: Path to Parquet file
            columns: Columns to read (None for all)
            
        Yields:
            DataFrame chunks
        """
        try:
            # Open file with PyArrow for memory mapping
            parquet_file = pq.ParquetFile(
                file_path,
                memory_map=True,
                pre_buffer=False,
            )
            
            # Get file metadata
            num_row_groups = parquet_file.metadata.num_row_groups
            total_rows = parquet_file.metadata.num_rows
            
            logger.info(
                f"Processing {file_path.name}: {total_rows:,} rows in "
                f"{num_row_groups} row groups"
            )
            
            # Process row groups
            rows_processed = 0
            
            for rg_idx in range(num_row_groups):
                # Read row group
                row_group = parquet_file.read_row_group(
                    rg_idx,
                    columns=columns,
                    use_threads=True,
                )
                
                # Convert to Polars DataFrame
                df = pl.from_arrow(row_group)
                
                # Process in chunks if row group is large
                rg_rows = len(df)
                if rg_rows > self.chunk_size:
                    for start_idx in range(0, rg_rows, self.chunk_size):
                        end_idx = min(start_idx + self.chunk_size, rg_rows)
                        chunk = df[start_idx:end_idx]
                        
                        yield chunk
                        
                        rows_processed += len(chunk)
                        self._manage_memory()
                else:
                    yield df
                    rows_processed += rg_rows
                    self._manage_memory()
                
                # Log progress
                if rows_processed % 1_000_000 == 0:
                    progress = (rows_processed / total_rows) * 100
                    logger.info(f"Progress: {rows_processed:,} / {total_rows:,} ({progress:.1f}%)")
            
            logger.info(f"Completed processing {file_path.name}")
            
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            raise
    
    def process_with_mmap(
        self,
        input_file: Path,
        output_file: Path,
        process_func,
        columns: Optional[list[str]] = None,
    ) -> dict:
        """
        Process file with memory mapping and write results.
        
        Args:
            input_file: Input Parquet file
            output_file: Output Parquet file
            process_func: Function to process each chunk
            columns: Columns to read
            
        Returns:
            Processing statistics
        """
        stats = {
            "total_rows": 0,
            "chunks_processed": 0,
            "bytes_processed": 0,
        }
        
        # Create output directory if needed
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize Parquet writer
        writer = None
        schema = None
        
        try:
            for chunk in self.read_parquet_mmap(input_file, columns):
                # Process chunk
                processed_chunk = process_func(chunk)
                
                # Initialize writer on first chunk
                if writer is None:
                    schema = processed_chunk.to_arrow().schema
                    writer = pq.ParquetWriter(
                        output_file,
                        schema,
                        compression="snappy",
                        use_dictionary=True,
                        data_page_size=1024 * 1024,  # 1MB pages
                    )
                
                # Write chunk
                writer.write_table(processed_chunk.to_arrow())
                
                # Update statistics
                stats["total_rows"] += len(processed_chunk)
                stats["chunks_processed"] += 1
                stats["bytes_processed"] += processed_chunk.estimated_size()
                
            # Close writer
            if writer:
                writer.close()
            
            logger.info(
                f"Wrote {stats['total_rows']:,} rows to {output_file.name}"
            )
            
        except Exception as e:
            logger.error(f"Processing failed: {e}")
            raise
        
        return stats
    
    def _manage_memory(self) -> None:
        """Manage memory with periodic garbage collection."""
        self.chunks_processed += 1
        
        # Periodic GC
        if self.chunks_processed % self.gc_interval == 0:
            gc.collect(0)
            
            # Check memory usage
            import psutil
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            if memory_mb > self.max_memory_bytes / 1024 / 1024:
                logger.warning(
                    f"Memory usage ({memory_mb:.1f}MB) exceeds limit, "
                    "forcing full GC"
                )
                gc.collect()
    
    def create_memory_mapped_array(
        self,
        shape: Tuple[int, ...],
        dtype: np.dtype,
        file_path: Optional[Path] = None,
    ) -> np.ndarray:
        """
        Create a memory-mapped numpy array.
        
        Args:
            shape: Array shape
            dtype: Data type
            file_path: Optional file path for persistence
            
        Returns:
            Memory-mapped array
        """
        if file_path:
            # Create persistent memory-mapped array
            return np.memmap(
                file_path,
                dtype=dtype,
                mode="w+",
                shape=shape,
            )
        else:
            # Create anonymous memory-mapped array
            return np.memmap(
                None,
                dtype=dtype,
                mode="w+",
                shape=shape,
            )
    
    def stream_sorted_merge(
        self,
        file_paths: list[Path],
        sort_column: str,
        output_file: Path,
        columns: Optional[list[str]] = None,
    ) -> dict:
        """
        Merge multiple sorted files with streaming.
        
        Args:
            file_paths: List of sorted input files
            sort_column: Column to merge on
            output_file: Output file path
            columns: Columns to include
            
        Returns:
            Merge statistics
        """
        stats = {
            "files_merged": len(file_paths),
            "total_rows": 0,
        }
        
        try:
            # Open all input files
            readers = []
            current_rows = []
            
            for file_path in file_paths:
                reader = self.read_parquet_mmap(file_path, columns)
                readers.append(reader)
                
                # Get first chunk from each reader
                try:
                    first_chunk = next(reader)
                    current_rows.append({
                        "reader_idx": len(readers) - 1,
                        "chunk": first_chunk,
                        "position": 0,
                    })
                except StopIteration:
                    pass
            
            # Initialize output writer
            writer = None
            schema = None
            
            # Merge with heap
            import heapq
            
            # Build initial heap
            heap = []
            for row_info in current_rows:
                chunk = row_info["chunk"]
                if len(chunk) > 0:
                    value = chunk[sort_column][0]
                    heapq.heappush(heap, (value, row_info))
            
            output_buffer = []
            buffer_size = 0
            
            while heap:
                # Get minimum value
                _, row_info = heapq.heappop(heap)
                chunk = row_info["chunk"]
                pos = row_info["position"]
                
                # Add row to buffer
                output_buffer.append(chunk[pos])
                buffer_size += 1
                
                # Flush buffer if full
                if buffer_size >= self.chunk_size:
                    output_df = pl.concat(output_buffer)
                    
                    if writer is None:
                        schema = output_df.to_arrow().schema
                        writer = pq.ParquetWriter(
                            output_file,
                            schema,
                            compression="snappy",
                        )
                    
                    writer.write_table(output_df.to_arrow())
                    stats["total_rows"] += len(output_df)
                    
                    output_buffer = []
                    buffer_size = 0
                    self._manage_memory()
                
                # Move to next row in chunk
                row_info["position"] += 1
                
                if row_info["position"] < len(chunk):
                    # More rows in current chunk
                    value = chunk[sort_column][row_info["position"]]
                    heapq.heappush(heap, (value, row_info))
                else:
                    # Need next chunk from reader
                    reader_idx = row_info["reader_idx"]
                    try:
                        next_chunk = next(readers[reader_idx])
                        if len(next_chunk) > 0:
                            row_info["chunk"] = next_chunk
                            row_info["position"] = 0
                            value = next_chunk[sort_column][0]
                            heapq.heappush(heap, (value, row_info))
                    except StopIteration:
                        pass
            
            # Flush remaining buffer
            if output_buffer:
                output_df = pl.concat(output_buffer)
                if writer is None:
                    schema = output_df.to_arrow().schema
                    writer = pq.ParquetWriter(
                        output_file,
                        schema,
                        compression="snappy",
                    )
                writer.write_table(output_df.to_arrow())
                stats["total_rows"] += len(output_df)
            
            if writer:
                writer.close()
            
            logger.info(
                f"Merged {stats['files_merged']} files into {output_file.name} "
                f"({stats['total_rows']:,} rows)"
            )
            
        except Exception as e:
            logger.error(f"Merge failed: {e}")
            raise
        
        return stats
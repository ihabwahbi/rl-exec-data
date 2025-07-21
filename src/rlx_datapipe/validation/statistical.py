"""Statistical validators for distribution comparison."""

from typing import Any, Optional, Union
import numpy as np
from scipy import stats
from loguru import logger

from .base import BaseValidator


class KSValidator(BaseValidator):
    """Two-sample Kolmogorov-Smirnov test validator."""
    
    def __init__(self, alpha: float = 0.05):
        """Initialize K-S validator.
        
        Args:
            alpha: Significance level for hypothesis test (default 0.05)
        """
        super().__init__(name="Kolmogorov-Smirnov Test", alpha=alpha)
        self._requires_full_data = True
    
    def _validate(self, sample1: np.ndarray, sample2: np.ndarray) -> tuple[bool, dict]:
        """Compare two samples using K-S test.
        
        Args:
            sample1: First sample array
            sample2: Second sample array
            
        Returns:
            Tuple of (passed, metrics)
        """
        # Ensure arrays
        sample1 = np.asarray(sample1)
        sample2 = np.asarray(sample2)
        
        # Run K-S test
        statistic, p_value = stats.ks_2samp(sample1, sample2)
        
        # Determine if test passes
        passed = p_value > self.config['alpha']
        
        # Calculate additional statistics
        metrics = {
            "statistic": float(statistic),
            "p_value": float(p_value),
            "alpha": self.config['alpha'],
            "sample1_size": len(sample1),
            "sample2_size": len(sample2),
            "sample1_mean": float(np.mean(sample1)),
            "sample2_mean": float(np.mean(sample2)),
            "sample1_std": float(np.std(sample1)),
            "sample2_std": float(np.std(sample2)),
            "interpretation": "Distributions are similar" if passed else "Distributions differ significantly"
        }
        
        logger.info(f"K-S test: statistic={statistic:.4f}, p_value={p_value:.4f}, passed={passed}")
        
        return passed, metrics


class PowerLawValidator(BaseValidator):
    """Validate trade size distribution follows power law."""
    
    def __init__(self, expected_alpha: float = 2.4, tolerance: float = 0.1):
        """Initialize power law validator.
        
        Args:
            expected_alpha: Expected power law exponent (default 2.4)
            tolerance: Acceptable deviation from expected (default 0.1)
        """
        super().__init__(
            name="Power Law Distribution", 
            expected_alpha=expected_alpha,
            tolerance=tolerance
        )
        self._requires_full_data = True
    
    def _validate(self, trade_sizes: np.ndarray, _: Any = None) -> tuple[bool, dict]:
        """Fit power law and validate exponent.
        
        Args:
            trade_sizes: Array of trade sizes
            _: Unused second parameter (for interface compatibility)
            
        Returns:
            Tuple of (passed, metrics)
        """
        try:
            import powerlaw
        except ImportError:
            logger.error("powerlaw package not installed. Run: pip install powerlaw")
            raise ImportError("powerlaw package required for PowerLawValidator")
        
        # Ensure array and positive values
        trade_sizes = np.asarray(trade_sizes)
        trade_sizes = trade_sizes[trade_sizes > 0]
        
        if len(trade_sizes) < 100:
            raise ValueError(f"Insufficient data: {len(trade_sizes)} positive trade sizes (need at least 100)")
        
        # Fit power law
        logger.info(f"Fitting power law to {len(trade_sizes)} trade sizes...")
        fit = powerlaw.Fit(trade_sizes, discrete=False, verbose=False)
        
        # Get alpha (exponent)
        alpha = fit.power_law.alpha
        xmin = fit.power_law.xmin
        
        # Compare with other distributions
        R_exp, p_exp = fit.distribution_compare('power_law', 'exponential')
        R_log, p_log = fit.distribution_compare('power_law', 'lognormal')
        
        # Check if within expected range
        expected = self.config['expected_alpha']
        tolerance = self.config['tolerance']
        passed = abs(alpha - expected) <= tolerance
        
        metrics = {
            "alpha": float(alpha),
            "xmin": float(xmin),
            "expected_alpha": expected,
            "tolerance": tolerance,
            "deviation": float(abs(alpha - expected)),
            "n_tail": int(fit.power_law.n_tail),
            "R_vs_exponential": float(R_exp) if R_exp is not None else None,
            "p_vs_exponential": float(p_exp) if p_exp is not None else None,
            "R_vs_lognormal": float(R_log) if R_log is not None else None,
            "p_vs_lognormal": float(p_log) if p_log is not None else None,
            "interpretation": f"Power law exponent {alpha:.3f} is {'within' if passed else 'outside'} expected range [{expected-tolerance:.3f}, {expected+tolerance:.3f}]"
        }
        
        logger.info(f"Power law fit: alpha={alpha:.3f}, xmin={xmin:.6f}, passed={passed}")
        
        return passed, metrics


class BasicStatsCalculator(BaseValidator):
    """Calculate basic statistical metrics for comparison."""
    
    def __init__(self, thresholds: Optional[dict] = None):
        """Initialize basic stats calculator.
        
        Args:
            thresholds: Optional dict of metric thresholds for pass/fail
        """
        default_thresholds = {
            "mean_relative_diff": 0.01,  # 1% difference in means
            "std_relative_diff": 0.05,    # 5% difference in std dev
            "median_relative_diff": 0.01   # 1% difference in medians
        }
        thresholds = thresholds or default_thresholds
        super().__init__(name="Basic Statistics Comparison", **thresholds)
        self._requires_full_data = True
    
    def _validate(self, data1: np.ndarray, data2: np.ndarray) -> tuple[bool, dict]:
        """Calculate and compare basic statistics.
        
        Args:
            data1: First dataset
            data2: Second dataset
            
        Returns:
            Tuple of (passed, metrics)
        """
        # Ensure arrays
        data1 = np.asarray(data1)
        data2 = np.asarray(data2)
        
        # Calculate statistics
        stats1 = {
            "mean": float(np.mean(data1)),
            "std": float(np.std(data1)),
            "median": float(np.median(data1)),
            "min": float(np.min(data1)),
            "max": float(np.max(data1)),
            "q25": float(np.percentile(data1, 25)),
            "q75": float(np.percentile(data1, 75)),
            "count": len(data1)
        }
        
        stats2 = {
            "mean": float(np.mean(data2)),
            "std": float(np.std(data2)),
            "median": float(np.median(data2)),
            "min": float(np.min(data2)),
            "max": float(np.max(data2)),
            "q25": float(np.percentile(data2, 25)),
            "q75": float(np.percentile(data2, 75)),
            "count": len(data2)
        }
        
        # Calculate relative differences
        mean_diff = abs(stats1["mean"] - stats2["mean"]) / max(abs(stats1["mean"]), 1e-10)
        std_diff = abs(stats1["std"] - stats2["std"]) / max(abs(stats1["std"]), 1e-10)
        median_diff = abs(stats1["median"] - stats2["median"]) / max(abs(stats1["median"]), 1e-10)
        
        # Check thresholds
        passed = True
        if "mean_relative_diff" in self.config:
            passed &= mean_diff <= self.config["mean_relative_diff"]
        if "std_relative_diff" in self.config:
            passed &= std_diff <= self.config["std_relative_diff"]
        if "median_relative_diff" in self.config:
            passed &= median_diff <= self.config["median_relative_diff"]
        
        metrics = {
            "sample1_stats": stats1,
            "sample2_stats": stats2,
            "mean_relative_diff": float(mean_diff),
            "std_relative_diff": float(std_diff),
            "median_relative_diff": float(median_diff),
            "thresholds": self.config,
            "interpretation": "Statistics are similar" if passed else "Statistics differ significantly"
        }
        
        logger.info(f"Basic stats: mean_diff={mean_diff:.4f}, std_diff={std_diff:.4f}, passed={passed}")
        
        return passed, metrics
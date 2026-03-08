import pandas as pd
import pytest
from poly_sniff.metrics.signal import compute_signal


def _make_df(rows):
    """Helper: build a metrics DataFrame from simplified row dicts."""
    return pd.DataFrame(rows)


class TestComputeSignal:
    def test_quiet_no_flagged(self):
        df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.5,
             'userDominantSideRatio': 0.6, 'userPriceConvictionScore': 0.1,
             'lateVolumeRatio': 0.1},
            {'proxyWallet': '0x2', 'userDirectionalConsistency': 0.4,
             'userDominantSideRatio': 0.5, 'userPriceConvictionScore': 0.2,
             'lateVolumeRatio': 0.05},
        ])
        result = compute_signal(df)
        assert result['signal_level'] == 'QUIET'
        assert result['flagged_count'] == 0

    def test_moderate_one_flagged(self):
        df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.90,
             'userDominantSideRatio': 0.95, 'userPriceConvictionScore': -0.1,
             'lateVolumeRatio': 0.6},
            {'proxyWallet': '0x2', 'userDirectionalConsistency': 0.4,
             'userDominantSideRatio': 0.5, 'userPriceConvictionScore': 0.2,
             'lateVolumeRatio': 0.05},
        ])
        result = compute_signal(df)
        assert result['signal_level'] == 'MODERATE'
        assert result['flagged_count'] == 1

    def test_strong_two_flagged(self):
        df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.90,
             'userDominantSideRatio': 0.95, 'userPriceConvictionScore': -0.1,
             'lateVolumeRatio': 0.6},
            {'proxyWallet': '0x2', 'userDirectionalConsistency': 0.88,
             'userDominantSideRatio': 0.92, 'userPriceConvictionScore': -0.05,
             'lateVolumeRatio': 0.55},
        ])
        result = compute_signal(df)
        assert result['signal_level'] == 'STRONG'
        assert result['flagged_count'] == 2

    def test_strong_one_flagged_high_late_volume(self):
        df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.90,
             'userDominantSideRatio': 0.95, 'userPriceConvictionScore': -0.1,
             'lateVolumeRatio': 0.75},
            {'proxyWallet': '0x2', 'userDirectionalConsistency': 0.4,
             'userDominantSideRatio': 0.5, 'userPriceConvictionScore': 0.2,
             'lateVolumeRatio': 0.05},
        ])
        result = compute_signal(df)
        assert result['signal_level'] == 'STRONG'
        assert result['flagged_count'] == 1

    def test_moderate_elevated_metrics_no_flagged(self):
        df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.80,
             'userDominantSideRatio': 0.70, 'userPriceConvictionScore': 0.1,
             'lateVolumeRatio': 0.35},
            {'proxyWallet': '0x2', 'userDirectionalConsistency': 0.78,
             'userDominantSideRatio': 0.65, 'userPriceConvictionScore': 0.05,
             'lateVolumeRatio': 0.40},
        ])
        result = compute_signal(df)
        assert result['signal_level'] == 'MODERATE'

    def test_anomaly_score_ordering(self):
        strong_df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.90,
             'userDominantSideRatio': 0.95, 'userPriceConvictionScore': -0.1,
             'lateVolumeRatio': 0.8},
            {'proxyWallet': '0x2', 'userDirectionalConsistency': 0.88,
             'userDominantSideRatio': 0.92, 'userPriceConvictionScore': -0.05,
             'lateVolumeRatio': 0.7},
        ])
        quiet_df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.3,
             'userDominantSideRatio': 0.5, 'userPriceConvictionScore': 0.2,
             'lateVolumeRatio': 0.05},
        ])
        strong = compute_signal(strong_df)
        quiet = compute_signal(quiet_df)
        assert strong['anomaly_score'] > quiet['anomaly_score']

    def test_empty_dataframe(self):
        df = pd.DataFrame(columns=['proxyWallet', 'userDirectionalConsistency',
                                    'userDominantSideRatio', 'userPriceConvictionScore',
                                    'lateVolumeRatio'])
        result = compute_signal(df)
        assert result['signal_level'] == 'QUIET'
        assert result['flagged_count'] == 0
        assert result['anomaly_score'] == 0

    def test_result_keys(self):
        df = _make_df([
            {'proxyWallet': '0x1', 'userDirectionalConsistency': 0.5,
             'userDominantSideRatio': 0.6, 'userPriceConvictionScore': 0.1,
             'lateVolumeRatio': 0.1},
        ])
        result = compute_signal(df)
        assert set(result.keys()) == {
            'signal_level', 'anomaly_score', 'flagged_count',
            'avg_directional', 'avg_late_volume', 'max_late_volume',
        }

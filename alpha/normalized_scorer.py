"""
Normalized Pair Scorer
"""


class NormalizedScorer:

    @staticmethod
    def normalize(value, minimum, maximum):

        if maximum == minimum:
            return 0

        return (value - minimum) / (maximum - minimum)

    @classmethod
    def score(cls, features, stats):

        score = 0

        score += cls.normalize(
            features["ce_volume"],
            stats["volume_min"],
            stats["volume_max"],
        )

        score += cls.normalize(
            features["pe_volume"],
            stats["volume_min"],
            stats["volume_max"],
        )

        score += cls.normalize(
            features["ce_oi"],
            stats["oi_min"],
            stats["oi_max"],
        )

        score += cls.normalize(
            features["pe_oi"],
            stats["oi_min"],
            stats["oi_max"],
        )

        score += cls.normalize(
            features["ce_iv"],
            stats["iv_min"],
            stats["iv_max"],
        )

        score += cls.normalize(
            features["pe_iv"],
            stats["iv_min"],
            stats["iv_max"],
        )

        score -= cls.normalize(
            features["ce_spread"],
            stats["spread_min"],
            stats["spread_max"],
        )

        score -= cls.normalize(
            features["pe_spread"],
            stats["spread_min"],
            stats["spread_max"],
        )

        return score
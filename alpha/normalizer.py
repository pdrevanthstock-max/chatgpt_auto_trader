"""
Normalizer
"""


class Normalizer:

    @staticmethod
    def normalize(value, minimum, maximum):

        if maximum == minimum:
            return 100

        return (
            (value - minimum)
            /
            (maximum - minimum)
        ) * 100
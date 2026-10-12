"""Test fixture: Agent 03 needs broker-signed sequence definitions before it
starts a sequence (owner decision 7a, 2026-10-11). Tests that exercise other
03 behavior give it a definition for whatever sequence id they use."""


class AnySequence(dict):
    DEFINITION = {"touches": [{"day": 0, "text": "Checking in - any questions?"},
                              {"day": 7, "text": "New listings this week in your area."}]}

    def get(self, key, default=None):
        return self.DEFINITION


def with_sequences(spoke):
    spoke.sequences = AnySequence()
    return spoke

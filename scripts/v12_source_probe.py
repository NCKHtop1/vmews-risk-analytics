"""Compatibility entrypoint for the V12 Phase-1 source probe.

The nine-phase workflow historically invokes this filename.  Research acquisition and
model validation are now separated, so this entrypoint delegates exclusively to the
fingerprint-verified immutable frozen snapshot probe.  It performs no live price-provider
or runtime price-network fetch.
"""
from v12_frozen_source_probe import main


if __name__ == "__main__":
    main()

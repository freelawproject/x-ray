import json
import sys

import xray

if __name__ == "__main__":
    bad_redactions = xray.inspect(sys.argv[1])
    print(json.dumps(bad_redactions, indent=2))

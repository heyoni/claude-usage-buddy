"""py2app 진입점. 묶인 앱 안에서는 이 파일이 곧 claude-usage-buddy 명령이다."""

import sys

from buddy.__main__ import main

sys.exit(main())

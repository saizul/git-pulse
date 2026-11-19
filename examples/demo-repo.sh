#!/usr/bin/env sh
# Create a small throw-away repository with a few authors, a pull request merge
# and a squash merge, then build a report for it:
#
#   sh examples/demo-repo.sh /tmp/pulse-demo && git-pulse report -C /tmp/pulse-demo
set -eu
dir=${1:-./pulse-demo}
rm -rf "$dir" && mkdir -p "$dir" && cd "$dir"
git init -q -b main

commit() { # commit <name> <email> <date> <message>
  GIT_AUTHOR_NAME=$1 GIT_AUTHOR_EMAIL=$2 GIT_AUTHOR_DATE=$3 \
  GIT_COMMITTER_NAME=$1 GIT_COMMITTER_EMAIL=$2 GIT_COMMITTER_DATE=$3 \
  git commit -q --allow-empty -m "$4"
}

printf 'def main():\n    print("hi")\n' > app.py && git add app.py
commit "Alice Anders" alice@example.com 2024-01-02T09:00:00+01:00 "Initial commit"
printf 'def main():\n    for x in range(3):\n        if x:\n            print(x)\n' > app.py && git add app.py
commit "Alice Anders" alice@example.com 2024-01-05T14:30:00+01:00 "Loop"
git checkout -q -b feature
printf 'def util():\n    return 1\n' > util.py && git add util.py
commit "Bob Brown" bob@example.com 2024-01-08T10:00:00-05:00 "Add util"
git checkout -q main
GIT_AUTHOR_DATE=2024-01-09T10:00:00Z GIT_COMMITTER_DATE=2024-01-09T10:00:00Z \
  git -c user.name="Alice Anders" -c user.email=alice@example.com \
  merge -q --no-ff -m "Merge pull request #1 from bob/feature" feature
printf '# demo\n' > README.md && git add README.md
commit "Carol Chen" carol@example.com 2024-02-11T22:15:00+00:00 "Add README (#2)"
echo "created $(git rev-list --count HEAD) commits in $dir"

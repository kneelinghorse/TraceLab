#!/usr/bin/env bash
#
# bump-version.sh - Bump tracelab-schemas version following semver
#
# Usage:
#   ./scripts/bump-version.sh patch   # 1.0.0 -> 1.0.1
#   ./scripts/bump-version.sh minor   # 1.0.0 -> 1.1.0
#   ./scripts/bump-version.sh major   # 1.0.0 -> 2.0.0
#   ./scripts/bump-version.sh 1.2.3   # Set explicit version
#
# After bumping:
#   1. Update CHANGELOG.md with the new version section
#   2. Commit changes
#   3. Create tag: git tag schemas-v<version>
#   4. Push: git push origin schemas-v<version>

set -euo pipefail

VERSION_FILE="tracelab_schemas/tracelab_schemas/version.py"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 <major|minor|patch|VERSION>"
    echo ""
    echo "Examples:"
    echo "  $0 patch     # 1.0.0 -> 1.0.1"
    echo "  $0 minor     # 1.0.0 -> 1.1.0"
    echo "  $0 major     # 1.0.0 -> 2.0.0"
    echo "  $0 1.2.3     # Set explicit version"
    exit 1
}

# Check we're in project root
if [ ! -f "$VERSION_FILE" ]; then
    echo -e "${RED}ERROR: Must run from project root (TraceLab/)${NC}"
    echo "Could not find: $VERSION_FILE"
    exit 1
fi

# Get argument
if [ $# -ne 1 ]; then
    usage
fi

BUMP_TYPE="$1"

# Get current version
CURRENT_VERSION=$(grep -oP '__version__ = "\K[^"]+' "$VERSION_FILE")
echo -e "Current version: ${YELLOW}$CURRENT_VERSION${NC}"

# Parse current version
IFS='.' read -r MAJOR MINOR PATCH <<< "${CURRENT_VERSION%%-*}"
PRERELEASE=""
if [[ "$CURRENT_VERSION" == *-* ]]; then
    PRERELEASE="-${CURRENT_VERSION#*-}"
fi

# Calculate new version
case "$BUMP_TYPE" in
    major)
        NEW_VERSION="$((MAJOR + 1)).0.0"
        ;;
    minor)
        NEW_VERSION="$MAJOR.$((MINOR + 1)).0"
        ;;
    patch)
        NEW_VERSION="$MAJOR.$MINOR.$((PATCH + 1))"
        ;;
    *)
        # Validate explicit version format
        if ! echo "$BUMP_TYPE" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$'; then
            echo -e "${RED}ERROR: Invalid version format: $BUMP_TYPE${NC}"
            echo "Expected: MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-prerelease"
            exit 1
        fi
        NEW_VERSION="$BUMP_TYPE"
        ;;
esac

echo -e "New version:     ${GREEN}$NEW_VERSION${NC}"

# Confirm if major bump
if [ "$BUMP_TYPE" = "major" ]; then
    echo ""
    echo -e "${YELLOW}WARNING: Major version bump indicates BREAKING CHANGES${NC}"
    echo "Ensure you have:"
    echo "  1. Documented breaking changes in CHANGELOG.md"
    echo "  2. Provided migration guide"
    echo "  3. Notified DeepSearch team"
    echo ""
    read -p "Continue? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# Update version.py
sed -i.bak "s/__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" "$VERSION_FILE"
rm -f "${VERSION_FILE}.bak"

echo ""
echo -e "${GREEN}Version updated to $NEW_VERSION${NC}"
echo ""
echo "Next steps:"
echo "  1. Update tracelab_schemas/CHANGELOG.md:"
echo "     - Move [Unreleased] items to [$NEW_VERSION] section"
echo "     - Add release date"
echo ""
echo "  2. Commit changes:"
echo "     git add tracelab_schemas/"
echo "     git commit -m \"chore: bump tracelab-schemas to $NEW_VERSION\""
echo ""
echo "  3. Create and push tag:"
echo "     git tag schemas-v$NEW_VERSION"
echo "     git push origin schemas-v$NEW_VERSION"
echo ""
echo "  4. The publish workflow will automatically:"
echo "     - Build the package"
echo "     - Publish to GitHub Packages"
echo "     - Create a GitHub Release"

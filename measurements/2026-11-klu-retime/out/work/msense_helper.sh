set -euo pipefail
cd /var/tmp/eda-job-rs-20261118T043815Z-17be3498-s00/src
REPO_ROOT="$PWD"
source sim/lib/msense_width.sh
read_msense_width design/netlist/bandgap_startup.spice
printf '%s' "$MSENSE_W"

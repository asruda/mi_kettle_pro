#!/bin/bash
set -e

component_name=mi_kettle_pro
ha_cs_config_file=configuration.yaml

# Check the number of input parameters.
if [ $# -ne 1 ]; then
    echo "usage: $0 [config_path]"
    exit 1
fi

config_path=$1
# Check if config path exists.
if [ ! -f "$config_path/$ha_cs_config_file" ]; then
    echo "$config_path is not HA Config Directory"
    exit 1
fi

# Get the script path.
script_path=$(dirname "$0")

# Set source and target
source_path="$script_path/custom_components/$component_name"
target_root="$config_path/custom_components"
target_path="$target_root/$component_name"

# Remove the old version.
rm -rf /tmp/$component_name
mv $target_path /tmp

# Copy the new version.
mkdir -p "$target_root"
cp -r "$source_path" "$target_path"

echo "Completed. Please restart Home Assistant."
exit 0
#!/usr/bin/env bash
# Espera a que termine la exportación y lanza nanoda.
until grep -q EXPORT_RC ~/nanoda/export.err 2>/dev/null; do sleep 30; done
if ! grep -q "EXPORT_RC=0" ~/nanoda/export.err; then echo "exportación falló; no se lanza nanoda"; exit 1; fi
cd ~/nanoda
/usr/bin/time -v ~/tools/nanoda_lib/target/release/nanoda_bin config.json > nanoda-out.txt 2> nanoda-time.err
echo "NANODA_RC=$?" >> nanoda-time.err

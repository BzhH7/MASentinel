#!/usr/bin/env bash
set -e

echo "[MASentinel][demo] step 1/5 analyze toy system"
python -m masentinel.cli analyze --config configs/toy.yaml --out outputs/toy/profile.json

echo "[MASentinel][demo] step 2/5 generate deterministic testcases"
python -m masentinel.cli generate --profile outputs/toy/profile.json --num-cases 12 --out outputs/toy/testcases.json

echo "[MASentinel][demo] step 3/5 execute testcases"
python -m masentinel.cli run --config configs/toy.yaml --testcases outputs/toy/testcases.json --out outputs/toy/runs --workers 1

echo "[MASentinel][demo] step 4/5 diagnose faults"
python -m masentinel.cli diagnose --profile outputs/toy/profile.json --testcases outputs/toy/testcases.json --traces outputs/toy/runs/traces --out outputs/toy/faults.json

echo "[MASentinel][demo] step 5/5 build reports"
python -m masentinel.cli report --profile outputs/toy/profile.json --testcases outputs/toy/testcases.json --traces outputs/toy/runs/traces --faults outputs/toy/faults.json --out outputs/toy/report

echo "[MASentinel][demo] done: outputs/toy/report.html"

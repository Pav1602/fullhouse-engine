"""Build bots/skantbot8.1/bot.py + harness/skantbot8.1_dev/bot.py from
skantbot8 (= 7.13 + #1) + the V81 sweep's best-trial Config-field overrides.

Mirrors the pattern of _build_714.py. For each best-trial param, replaces
the dataclass default in the Config block. Leaves untouched params at
their skantbot8 values.

Usage:
    python _build_v81_best.py
"""
import re, sys, json
sys.path.insert(0, ".")


def best_params_from_study():
    import optuna
    study = optuna.load_study(
        study_name="skb8_v81",
        storage="sqlite:///harness/results/skb8_v81.db",
    )
    bt = study.best_trial
    print(f"Best trial #{bt.number}: score={bt.value:.2f}")
    return dict(bt.params), bt.value, dict(bt.user_attrs)


def rewrite(src, dst, params):
    with open(src) as f:
        lines = f.readlines()
    found_config = False
    end_config = False
    n_rewritten = 0
    rewritten_names = set()
    for i, line in enumerate(lines):
        if "class Config:" in line:
            found_config = True
            continue
        if not found_config or end_config:
            continue
        stripped = line.strip()
        if stripped.startswith("CONFIG ") or stripped.startswith("def load_config_from_env"):
            end_config = True
            continue
        # Match: `    name: type = value  # comment`
        m = re.match(
            r"^(\s+)(\w+)(\s*:\s*\w+(?:\[\w+\])?\s*=\s*)([\d.eE+-]+)(.*)$",
            line,
        )
        if not m:
            continue
        indent, name, middle, old_val, tail = m.groups()
        if name not in params:
            continue
        new_val = params[name]
        # Match dataclass field's natural type
        if "." in old_val or "e" in old_val.lower():
            new_val_str = f"{float(new_val):.16f}".rstrip("0").rstrip(".")
            if "." not in new_val_str:
                new_val_str += ".0"
        else:
            new_val_str = str(int(new_val))
        lines[i] = f"{indent}{name}{middle}{new_val_str}{tail}\n"
        rewritten_names.add(name)
        n_rewritten += 1

    missed = set(params) - rewritten_names
    if missed:
        print(f"WARN: params not found in Config: {sorted(missed)}")
    print(f"  {src} -> {dst}: rewrote {n_rewritten} fields")
    with open(dst, "w") as f:
        f.writelines(lines)


def main():
    import os
    params, score, user_attrs = best_params_from_study()
    print(f"  train_mean: {user_attrs.get('train_mean')}")
    print(f"  held_min:   {user_attrs.get('held_min')}")
    print(f"  held_mean:  {user_attrs.get('held_mean')}")

    os.makedirs("bots/skantbot8.1", exist_ok=True)
    os.makedirs("harness/skantbot8.1_dev", exist_ok=True)
    rewrite("bots/skantbot8/bot.py",
            "bots/skantbot8.1/bot.py", params)
    rewrite("harness/skantbot8_dev/bot.py",
            "harness/skantbot8.1_dev/bot.py", params)
    with open("harness/results/skb8_1_build_params.json", "w") as f:
        json.dump({
            "best_score": score,
            "best_params": params,
            "user_attrs": user_attrs,
        }, f, indent=2, default=str)
    print("\nSaved params: harness/results/skb8_1_build_params.json")


if __name__ == "__main__":
    main()

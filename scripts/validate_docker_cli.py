"""Record Docker identity and validate the packaged CLI under a 1 GB cap."""

import argparse
import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="ad-aggregator:scalability")
    parser.add_argument("--volume", default="ad-aggregator-scalability-v1")
    parser.add_argument(
        "--study",
        type=Path,
        default=Path("benchmarks/docker-linux-scalability.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("benchmarks/docker-linux-verification.json"),
    )
    args = parser.parse_args()
    study = json.loads(args.study.read_text())
    if not study["complete"]:
        raise ValueError("Study is incomplete")
    info = json.loads(docker("info", "--format", "{{json .}}"))
    image = json.loads(docker("image", "inspect", args.image))[0]
    report = {
        "build_command": ["docker", "build", "-t", args.image, "."],
        "image": {
            k: image[k]
            for k in (
                "Id",
                "RepoTags",
                "RepoDigests",
                "Created",
                "Os",
                "Architecture",
            )
        },
        "docker": {
            key: info[key]
            for key in (
                "ServerVersion",
                "OperatingSystem",
                "OSType",
                "Architecture",
                "KernelVersion",
                "NCPU",
                "MemTotal",
                "CgroupVersion",
                "ContainersRunning",
            )
        },
        "host": platform.platform(),
        "source_sha256": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                Path("Dockerfile"),
                Path("uv.lock"),
                Path("pyproject.toml"),
                Path(__file__),
            ]
        },
        "protected_sha256": {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in map(
                Path, ["AGENTS.md", "REQUIREMENTS.md", "PROMPTS.md"]
            )
        },
        "cli_runs": [],
    }
    for dataset in study["datasets"]:
        cardinality = dataset["expected"]["campaigns"]
        if cardinality not in (50, 100000):
            continue
        name = f"ad-scalability-cli-{cardinality}"
        output = f"/study/cli-output/{cardinality}"
        command = [
            "create",
            "--name",
            name,
            "--cpus",
            "16",
            "--memory",
            "1000000000",
            "--memory-swap",
            "1000000000",
            "--env",
            "POLARS_MAX_THREADS=16",
            "--mount",
            f"type=volume,src={args.volume},dst=/study",
            args.image,
            "--input",
            dataset["input"],
            "--output",
            output,
        ]
        identifier = docker(*command)
        start = time.perf_counter()
        logs = docker("start", "--attach", identifier)
        seconds = time.perf_counter() - start
        state = json.loads(docker("inspect", identifier))[0]
        run = {
            "campaigns": cardinality,
            "command": ["docker", *command],
            "container_id": identifier,
            "start_attach_wall_seconds": seconds,
            "logs": logs,
            "state": state["State"],
            "memory_limit_bytes": state["HostConfig"]["Memory"],
            "memory_plus_swap_limit_bytes": state["HostConfig"]["MemorySwap"],
        }
        report["cli_runs"].append(run)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        if state["State"]["ExitCode"] or state["State"]["OOMKilled"]:
            raise RuntimeError(f"CLI failed: {run}")
        code = (
            "import hashlib,json; from pathlib import Path; "
            f"p=Path({output!r}); "
            "print(json.dumps({f.name:"
            "hashlib.sha256(f.read_bytes()).hexdigest() "
            "for f in p.glob('*.csv')}))"
        )
        hashes = json.loads(
            docker(
                "run",
                "--rm",
                "--mount",
                f"type=volume,src={args.volume},dst=/study,readonly",
                "--entrypoint",
                "python",
                args.image,
                "-c",
                code,
            )
        )
        if hashes != dataset["expected"]["output_sha256"]:
            raise ValueError("CLI output differs from independent reference")
        run["output_sha256"] = hashes
        docker("rm", identifier)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(
            f"CLI {cardinality}: passed 1 GB cap, {seconds:.3f}s", flush=True
        )
    report["complete"] = True
    args.report.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()

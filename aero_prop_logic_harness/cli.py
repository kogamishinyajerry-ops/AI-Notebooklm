"""
Command Line Interface (CLI) for AeroProp Logic Harness.

Provides core validation, checking, and reporting commands.
"""

from pathlib import Path
import typer
from rich.console import Console

from aero_prop_logic_harness.validators import (
    SchemaValidator,
    TraceValidator,
    ConsistencyValidator,
)
from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry
from aero_prop_logic_harness.path_constants import is_formal_baseline_root
from aero_prop_logic_harness import __version__

app = typer.Typer(
    name="aplh",
    help="AeroProp Logic Harness CLI - Knowledge engineering for propulsion control logic.",
    add_completion=False,
)
console = Console()


@app.command()
def version():
    """Print the version."""
    console.print(f"AeroProp Logic Harness (APLH) v{__version__}")


@app.command()
def validate_artifacts(
    directory: Path = typer.Option(
        Path("artifacts"),
        "--dir", "-d",
        help="Directory containing artifacts to validate"
    )
):
    """Validate all artifact file schemas and structural integrity."""
    console.print(f"[bold cyan]Validating schemas in {directory}...[/bold cyan]")
    
    validator = SchemaValidator()
    is_valid = validator.validate_directory(directory)
    
    console.print(validator.get_report())
    
    if not is_valid:
        raise typer.Exit(code=1)


@app.command()
def check_trace(
    directory: Path = typer.Option(
        Path("artifacts"),
        "--dir", "-d",
        help="Directory containing artifacts and traces"
    )
):
    """Check trace link consistency and endpoints."""
    console.print(f"[bold cyan]Checking trace consistency in {directory}...[/bold cyan]")
    
    # 1. Load everything into registry
    registry = ArtifactRegistry()
    try:
        registry.load_from_directory(directory)
    except Exception as e:
        console.print(f"[bold red]Error loading artifacts:[/bold red] {e}")
        raise typer.Exit(code=1)
        
    console.print(f"Loaded {len(registry.artifacts)} artifacts and {len(registry.traces)} traces.")

    # 2. Schema check already passed if we loaded them, now check traces
    trace_validator = TraceValidator(registry)
    traces_ok = trace_validator.validate_all()
    console.print(trace_validator.get_report())
    
    # 3. Check broader consistency (embedded links, etc.)
    consist_validator = ConsistencyValidator(registry)
    consist_ok = consist_validator.validate_all()
    console.print(consist_validator.get_report())
    
    if not (traces_ok and consist_ok):
        raise typer.Exit(code=1)


@app.command()
def list_artifacts(
    directory: Path = typer.Option(
        Path("artifacts"),
        "--dir", "-d",
        help="Directory to list from"
    )
):
    """List all valid artifacts found, grouped by type."""
    registry = ArtifactRegistry()
    registry.load_from_directory(directory)
    
    if not registry.artifacts and not registry.traces:
        console.print("No artifacts found.")
        return
        
    for art_type, items in registry.by_type.items():
        console.print(f"\n[bold]{art_type.upper()}[/bold] ({len(items)} items)")
        for item in sorted(items, key=lambda x: x.id):
            title = getattr(item, 'title', getattr(item, 'name', getattr(item, 'term', '')))
            console.print(f"  {item.id}: {title} [{item.review_status.value}]")
            
    if registry.traces:
        console.print(f"\n[bold]TRACE LINKS[/bold] ({len(registry.traces)} items)")
        for _, trace in sorted(registry.traces.items()):
            console.print(f"  {trace.id}: {trace.source_id} --{trace.link_type.value}--> {trace.target_id}")


@app.command()
def freeze_readiness(
    directory: Path = typer.Option(
        Path("artifacts"),
        "--dir", "-d",
        help="Directory to assess"
    )
):
    """Assess whether the current artifact set is ready for a baseline freeze."""
    console.print("[bold cyan]Assessing Freeze Readiness...[/bold cyan]")
    
    # Needs to pass schema & trace first
    registry = ArtifactRegistry()
    try:
        registry.load_from_directory(directory)
    except Exception as e:
        console.print(f"[bold red]Cannot assess freeze readiness. Load failed: {e}[/bold red]")
        raise typer.Exit(code=1)
        
    trace_validator = TraceValidator(registry)
    consist_validator = ConsistencyValidator(registry)
    
    schema_ok = True  # If it loaded, basic schema is ok
    traces_ok = trace_validator.validate_all()
    consist_ok = consist_validator.validate_all()
    
    # Empty trace check
    empty_graph = len(registry.traces) == 0
    traces_ok = traces_ok and not empty_graph
    
    # Relational Topology Coverage Check
    relations = {
        "REQ->FUNC": False,
        "REQ->IFACE": False,
        "REQ->ABN": False,
        "FUNC->IFACE": False,
        "ABN->FUNC_OR_IFACE": False,
    }
    
    for trace in registry.traces.values():
        src_prefix = trace.source_id.split("-")[0]
        tgt_prefix = trace.target_id.split("-")[0]
        
        if src_prefix == "REQ" and tgt_prefix == "FUNC":
            relations["REQ->FUNC"] = True
        elif src_prefix == "REQ" and tgt_prefix == "IFACE":
            relations["REQ->IFACE"] = True
        elif src_prefix == "REQ" and tgt_prefix == "ABN":
            relations["REQ->ABN"] = True
        elif src_prefix == "FUNC" and tgt_prefix == "IFACE":
            relations["FUNC->IFACE"] = True
        elif src_prefix == "ABN" and tgt_prefix in ("FUNC", "IFACE"):
            relations["ABN->FUNC_OR_IFACE"] = True
            
    coverage_ok = all(relations.values())
    missing_relations = [k for k, v in relations.items() if not v]
    
    # Assess drafts, low confidence, and orphans
    unreviewed = 0
    low_confidence = 0
    orphans = 0
    
    for art_id, art in registry.artifacts.items():
        if art.review_status.value in ("draft", "rejected"):
            unreviewed += 1
        if art.provenance.confidence < 0.8:
            low_confidence += 1
        if registry.is_orphan(art_id):
            orphans += 1
            
    # Checklist verification via machine-readable YAML bound to TARGET_DIR
    checklist_ok = False
    checklist_path = Path(directory) / ".aplh" / "freeze_gate_status.yaml"
    baseline_scope = None
    formal_boundary_ok = True  # pessimistic flip below when needed

    console.print(f"[bold]Evaluating Signoff Boundary:[/bold] {checklist_path.absolute()}")

    if checklist_path.is_file():
        from aero_prop_logic_harness.loaders.yaml_loader import load_yaml
        from aero_prop_logic_harness.models import FreezeGateStatus
        from pydantic import ValidationError
        try:
            data = load_yaml(checklist_path)
            signoff = FreezeGateStatus(**data)
            baseline_scope = signoff.baseline_scope
            if signoff.boundary_frozen and signoff.schema_frozen and signoff.trace_gate_passed and signoff.baseline_review_complete:
                checklist_ok = True
        except (ValueError, ValidationError) as e:
            checklist_ok = False
            console.print(f"[red]Signoff schema validation failed: {str(e)}[/red]")
    else:
        checklist_ok = False
        console.print(f"[red]Error: Target baseline must contain '.aplh/freeze_gate_status.yaml'.[/red]")

    # ── P1: Formal / demo boundary programmatic enforcement ───────────
    # `freeze-complete` scope is ONLY valid when the target directory is
    # the repository's formal baseline root.  This is a hard programme
    # constraint — the YAML signoff field alone cannot grant formal
    # status.  Any non-formal directory claiming `freeze-complete` is
    # rejected with an explicit error.
    if baseline_scope and baseline_scope.value == "freeze-complete":
        if not is_formal_baseline_root(Path(directory)):
            formal_boundary_ok = False
            console.print(
                "[bold red]Formal boundary violation: "
                "baseline_scope is 'freeze-complete' but the target directory "
                f"({Path(directory).resolve()}) is NOT the formal baseline root. "
                "freeze-complete is only valid for the repository's artifacts/ root.[/bold red]"
            )

    console.print("\n[bold]Readiness Report:[/bold]")
    console.print(f"  Load & Schema: {'✅ Pass' if schema_ok else '❌ Fail'}")
    console.print(f"  Trace Graph Semantics: {'✅ Pass' if traces_ok and consist_ok else '❌ Fail'}")
    console.print(f"  Empty Graph Check: {'✅ Pass' if not empty_graph else f'❌ Fail (0 traces)'}")
    console.print(f"  Min Relational Coverage: {'✅ Pass' if coverage_ok else '❌ Fail'}")
    console.print(f"  Orphan Artifacts: {'✅ Pass' if orphans == 0 else f'❌ Fail ({orphans} orphans)'}")
    console.print(f"  Unreviewed Artifacts: {'✅ Pass' if unreviewed == 0 else f'❌ Fail ({unreviewed} artifacts)'}")
    console.print(f"  Low Confidence (<0.8): {'✅ Pass' if low_confidence == 0 else f'❌ Fail ({low_confidence} artifacts)'}")
    console.print(f"  Checklist Completed: {'✅ Pass' if checklist_ok else '❌ Fail (Docs incomplete)'}")
    console.print(f"  Formal Boundary: {'✅ Pass' if formal_boundary_ok else '❌ Fail (not formal baseline root)'}")

    ready = (
        schema_ok and traces_ok and consist_ok
        and unreviewed == 0 and low_confidence == 0 and orphans == 0
        and coverage_ok and checklist_ok and not empty_graph
        and formal_boundary_ok
    )


    if ready:
        if baseline_scope and baseline_scope.value == "demo-scale":
            console.print("\n[yellow]✅ Demo-scale gate checks passed (Not for formal freeze)[/yellow]")
        else:
            console.print("\n[bold green]✅ Ready for Formal Baseline Freeze![/bold green]")
    else:
        console.print("\n[bold red]❌ Not ready for freeze. Please address the issues above.[/bold red]")
        raise typer.Exit(code=1)


def _classify_directory(target_dir: Path) -> str:
    """Classify a target directory into one of three scopes per §6.5.

    Returns one of: '[Formal]', '[Demo-scale]', '[Unmanaged]'.
    """
    if is_formal_baseline_root(target_dir):
        return "[Formal]"

    # Check for baseline-local .aplh/freeze_gate_status.yaml
    gate_file = Path(target_dir) / ".aplh" / "freeze_gate_status.yaml"
    if gate_file.is_file():
        try:
            from aero_prop_logic_harness.loaders.yaml_loader import load_yaml
            from aero_prop_logic_harness.models import FreezeGateStatus
            data = load_yaml(gate_file)
            status = FreezeGateStatus(**data)
            if status.baseline_scope and status.baseline_scope.value == "demo-scale":
                return "[Demo-scale]"
        except Exception:
            pass

    return "[Unmanaged]"


@app.command()
def validate_modes(
    directory: Path = typer.Option(
        Path("artifacts"),
        "--dir", "-d",
        help="Directory containing mode/transition/guard artifacts to validate"
    ),
    coverage: bool = typer.Option(
        False,
        "--coverage",
        help="Also run coverage validation (ABN coverage, degraded/emergency checks)"
    ),
):
    """Validate mode graph structure, reachability, and (optionally) coverage."""
    from aero_prop_logic_harness.services.mode_graph import ModeGraph
    from aero_prop_logic_harness.validators.mode_validator import ModeValidator
    from aero_prop_logic_harness.validators.coverage_validator import CoverageValidator

    if not directory.is_dir():
        console.print(f"[bold red]Error: Directory does not exist: {directory}[/bold red]")
        raise typer.Exit(code=1)

    # Classify directory scope
    scope_label = _classify_directory(directory)
    console.print(f"{scope_label} {directory}")

    # Load artifacts
    registry = ArtifactRegistry()
    try:
        registry.load_from_directory(directory)
    except Exception as e:
        console.print(f"[bold red]Error loading artifacts:[/bold red] {e}")
        raise typer.Exit(code=1)

    # Build mode graph
    graph = ModeGraph.from_registry(registry)
    console.print(
        f"Found: {graph.mode_count} modes, "
        f"{graph.transition_count} transitions, "
        f"{graph.guard_count} guards"
    )

    # If no Phase 2 artifacts, early exit with success
    if graph.mode_count == 0 and graph.transition_count == 0 and graph.guard_count == 0:
        console.print("Mode graph validation not applicable — no Phase 2 artifacts found.")
        raise typer.Exit(code=0)

    # Run mode validator
    mode_val = ModeValidator(registry, graph)
    mode_ok = mode_val.validate_all()
    console.print(mode_val.get_report())

    # Optionally run coverage validator
    coverage_ok = True
    if coverage:
        cov_val = CoverageValidator(registry, graph)
        coverage_ok = cov_val.validate_all()
        console.print(cov_val.get_report())

    if not (mode_ok and coverage_ok):
        raise typer.Exit(code=1)

    # Scope-appropriate success message
    if scope_label == "[Formal]":
        console.print("[bold green]Formal mode graph checks passed.[/bold green]")
    elif scope_label == "[Demo-scale]":
        console.print("[yellow]Demo-scale mode graph checks passed.[/yellow]")
    else:
        console.print("Unmanaged mode graph checks passed.")


@app.command()
def run_scenario(
    directory: Path = typer.Option(
        Path("artifacts"),
        "--dir", "-d",
        help="Directory containing ModeGraph artifacts"
    ),
    scenario_file: Path = typer.Option(
        ...,
        "--scenario", "-s",
        help="Path to scenario YAML file"
    ),
    richer: bool = typer.Option(
        False,
        "--richer",
        help="Enable Phase 3-3 RicherEvaluator (DELTA_*, IN_RANGE, SUSTAINED_*, HYSTERESIS_BAND)"
    ),
):
    """Run a demo-scale scenario against the ModeGraph."""
    from aero_prop_logic_harness.loaders.yaml_loader import load_yaml
    from aero_prop_logic_harness.models.scenario import Scenario
    from aero_prop_logic_harness.services.mode_graph import ModeGraph
    from aero_prop_logic_harness.services.scenario_engine import ScenarioEngine

    if not directory.is_dir():
        console.print(f"[bold red]Error: Directory does not exist: {directory}[/bold red]")
        raise typer.Exit(code=1)
        
    scope_label = _classify_directory(directory)
    if scope_label == "[Formal]":
        console.print("[bold red]Formal directory execution is not allowed in 2C. Use demo-scale.[/bold red]")
        raise typer.Exit(code=1)
        
    if not scenario_file.is_file():
        console.print(f"[bold red]Error: Scenario file does not exist: {scenario_file}[/bold red]")
        raise typer.Exit(code=1)
        
    try:
        data = load_yaml(scenario_file)
        scenario = Scenario(**data)
    except Exception as e:
        console.print(f"[bold red]Error loading scenario:[/bold red] {e}")
        raise typer.Exit(code=1)
        
    registry = ArtifactRegistry()
    try:
        registry.load_from_directory(directory)
    except Exception as e:
        console.print(f"[bold red]Error loading artifacts:[/bold red] {e}")
        raise typer.Exit(code=1)

    graph = ModeGraph.from_registry(registry)

    # Phase 3-3: optionally inject RicherEvaluator
    evaluator = None
    if richer:
        from aero_prop_logic_harness.services.richer_evaluator import RicherEvaluator
        evaluator = RicherEvaluator()
        console.print("[cyan]RicherEvaluator enabled (Phase 3-3)[/cyan]")

    engine = ScenarioEngine(graph, evaluator=evaluator)
    console.print(f"Running scenario [cyan]{scenario.scenario_id}[/cyan]: {scenario.title}")
    
    trace = engine.run_scenario(scenario)
    trace.evaluator_mode = "richer" if richer else "baseline"
    
    # Phase 3: display run_id for audit correlation
    console.print(f"Run ID: [cyan]{engine.run_id}[/cyan]")
    console.print(trace.to_human_readable())

    # Phase 3-2: persist trace to .aplh/traces/
    if scope_label == "[Demo-scale]":
        from aero_prop_logic_harness.services.replay_reader import save_trace
        trace_path = save_trace(trace, directory)
        console.print(f"Trace saved: {trace_path}")

    if engine.state and engine.state.blocked_by_t2:
        console.print(f"\n[bold red]Execution halted: {engine.state.halt_reason}[/bold red]")
        console.print(
            f"This requires T2 review. Run:\n"
            f"  aplh signoff-demo --dir {directory} --reviewer '<name>' "
            f"--scenario-id {scenario.scenario_id} --run-id {engine.run_id} "
            f"--resolution '<decision>'"
        )
        raise typer.Exit(code=1)
    else:
        console.print("\n[bold green]Scenario execution completed successfully.[/bold green]")


@app.command()
def validate_scenario(
    directory: Path = typer.Option(
        Path("artifacts"),
        "--dir", "-d",
        help="Directory containing ModeGraph artifacts"
    ),
    scenario_file: Path = typer.Option(
        ...,
        "--scenario", "-s",
        help="Path to scenario YAML file"
    ),
):
    """Validate a scenario file against the ModeGraph (structural pre-check)."""
    from aero_prop_logic_harness.loaders.yaml_loader import load_yaml
    from aero_prop_logic_harness.models.scenario import Scenario
    from aero_prop_logic_harness.services.mode_graph import ModeGraph
    from aero_prop_logic_harness.services.scenario_validator import ScenarioValidator

    if not directory.is_dir():
        console.print(f"[bold red]Error: Directory does not exist: {directory}[/bold red]")
        raise typer.Exit(code=1)

    scope_label = _classify_directory(directory)
    if scope_label == "[Formal]":
        console.print("[bold red]Formal directory scenario validation is not allowed. Use demo-scale.[/bold red]")
        raise typer.Exit(code=1)

    if not scenario_file.is_file():
        console.print(f"[bold red]Error: Scenario file does not exist: {scenario_file}[/bold red]")
        raise typer.Exit(code=1)

    try:
        data = load_yaml(scenario_file)
        scenario = Scenario(**data)
    except Exception as e:
        console.print(f"[bold red]Error loading scenario:[/bold red] {e}")
        raise typer.Exit(code=1)

    registry = ArtifactRegistry()
    try:
        registry.load_from_directory(directory)
    except Exception as e:
        console.print(f"[bold red]Error loading artifacts:[/bold red] {e}")
        raise typer.Exit(code=1)

    graph = ModeGraph.from_registry(registry)
    validator = ScenarioValidator(graph)
    result = validator.validate(scenario)

    console.print(result.to_report())

    if not result.passed:
        raise typer.Exit(code=1)
    else:
        console.print("[bold green]Scenario validation passed.[/bold green]")


@app.command()
def replay_scenario(
    directory: Path = typer.Option(
        Path("artifacts"),
        "--dir", "-d",
        help="Directory containing the demo baseline"
    ),
    scenario_file: Path = typer.Option(
        ...,
        "--scenario", "-s",
        help="Path to scenario YAML file to replay"
    ),
    trace_file: Path = typer.Option(
        ...,
        "--trace", "-t",
        help="Path to expected trace YAML file"
    ),
    richer: bool = typer.Option(
        False,
        "--richer",
        help="Enable Phase 3-3 RicherEvaluator for replay"
    ),
):
    """Replay a scenario and compare with an expected trace for deterministic consistency."""
    from aero_prop_logic_harness.loaders.yaml_loader import load_yaml
    from aero_prop_logic_harness.models.scenario import Scenario
    from aero_prop_logic_harness.services.mode_graph import ModeGraph
    from aero_prop_logic_harness.services.replay_reader import (
        ReplayReader,
        load_trace,
    )

    if not directory.is_dir():
        console.print(f"[bold red]Error: Directory does not exist: {directory}[/bold red]")
        raise typer.Exit(code=1)

    scope_label = _classify_directory(directory)
    if scope_label == "[Formal]":
        console.print("[bold red]Formal directory replay is not allowed. Use demo-scale.[/bold red]")
        raise typer.Exit(code=1)

    if not scenario_file.is_file():
        console.print(f"[bold red]Error: Scenario file does not exist: {scenario_file}[/bold red]")
        raise typer.Exit(code=1)

    if not trace_file.is_file():
        console.print(f"[bold red]Error: Trace file does not exist: {trace_file}[/bold red]")
        raise typer.Exit(code=1)

    try:
        data = load_yaml(scenario_file)
        scenario = Scenario(**data)
    except Exception as e:
        console.print(f"[bold red]Error loading scenario:[/bold red] {e}")
        raise typer.Exit(code=1)

    try:
        expected_trace = load_trace(trace_file)
    except Exception as e:
        console.print(f"[bold red]Error loading trace:[/bold red] {e}")
        raise typer.Exit(code=1)

    registry = ArtifactRegistry()
    try:
        registry.load_from_directory(directory)
    except Exception as e:
        console.print(f"[bold red]Error loading artifacts:[/bold red] {e}")
        raise typer.Exit(code=1)

    graph = ModeGraph.from_registry(registry)

    # Phase 3-3: optionally inject RicherEvaluator for replay
    evaluator = None
    if richer:
        from aero_prop_logic_harness.services.richer_evaluator import RicherEvaluator
        evaluator = RicherEvaluator()
        console.print("[cyan]RicherEvaluator enabled for replay (Phase 3-3)[/cyan]")

    console.print(
        f"Replaying scenario [cyan]{scenario.scenario_id}[/cyan] "
        f"against trace from run [cyan]{expected_trace.run_id}[/cyan]"
    )

    result = ReplayReader.replay_and_compare(scenario, graph, expected_trace, evaluator=evaluator)

    if result.match:
        console.print("[bold green]Replay matched — deterministic consistency confirmed.[/bold green]")
    else:
        console.print(f"[bold red]Replay diverged![/bold red]")
        if result.divergence_tick is not None:
            console.print(f"  First divergence at tick: {result.divergence_tick}")
        console.print(f"  Detail: {result.divergence_detail}")
        raise typer.Exit(code=1)


@app.command()
def inspect_run(
    directory: Path = typer.Option(
        Path("artifacts"),
        "--dir", "-d",
        help="Directory containing the demo baseline"
    ),
    run_id: str = typer.Option(
        ...,
        "--run-id",
        help="Run ID to inspect (e.g., RUN-3A7F1BC9D2E4)"
    ),
):
    """Inspect a persisted run trace by run_id — tick-by-tick readback."""
    from aero_prop_logic_harness.services.replay_reader import (
        ReplayReader,
        find_trace_by_run_id,
        load_trace,
    )

    if not directory.is_dir():
        console.print(f"[bold red]Error: Directory does not exist: {directory}[/bold red]")
        raise typer.Exit(code=1)

    scope_label = _classify_directory(directory)
    if scope_label == "[Formal]":
        console.print("[bold red]Formal directory inspection is not allowed. Use demo-scale.[/bold red]")
        raise typer.Exit(code=1)

    trace_path = find_trace_by_run_id(directory, run_id)
    if trace_path is None:
        console.print(f"[bold red]No trace found for run_id: {run_id}[/bold red]")
        raise typer.Exit(code=1)

    trace = load_trace(trace_path)
    console.print(f"[bold]Trace file:[/bold] {trace_path}")
    console.print(f"[bold]Run ID:[/bold] {trace.run_id}")
    console.print(f"[bold]Scenario ID:[/bold] {trace.scenario_id}")
    console.print(f"[bold]Records:[/bold] {len(trace.records)}")
    console.print("")

    readback = ReplayReader.readback(trace)
    for entry in readback:
        console.print(f"Tick {entry['tick_id']}:")
        console.print(f"  Mode: {entry['mode_before']} → {entry['mode_after']}")
        if entry['transition_selected']:
            console.print(f"  Transition: {entry['transition_selected']}")
        if entry['actions_emitted']:
            console.print(f"  Actions: {entry['actions_emitted']}")
        if entry['block_reason']:
            console.print(f"  [BLOCKED] {entry['block_reason']}")
        if not entry['transition_selected'] and not entry['block_reason']:
            console.print(f"  (No transition)")

    # Check signoff correlation
    signoff_file = directory / ".aplh" / "review_signoffs.yaml"
    if signoff_file.is_file():
        import ruamel.yaml as ry
        yaml_loader = ry.YAML(typ="safe")
        with open(signoff_file) as f:
            signoffs = yaml_loader.load(f) or []
        related = [s for s in signoffs if isinstance(s, dict) and s.get("run_id") == run_id]
        if related:
            console.print(f"\n[bold]Related signoffs:[/bold] {len(related)}")
            for s in related:
                console.print(
                    f"  [{s.get('timestamp', '?')}] "
                    f"reviewer={s.get('reviewer', '?')} "
                    f"resolution={s.get('resolution', '?')}"
                )
        else:
            console.print(f"\nNo signoffs found for run_id {run_id}.")


@app.command()
def signoff_demo(
    directory: Path = typer.Option(
        ...,
        "--dir", "-d",
        help="Directory containing the demo baseline to sign off"
    ),
    resolution: str = typer.Option(
        ...,
        "--resolution", "-r",
        help="The manual resolution string for the T2 block"
    ),
    reviewer: str = typer.Option(
        ...,
        "--reviewer",
        help="Identity of the human reviewer approving this signoff"
    ),
    scenario_id: str = typer.Option(
        None,
        "--scenario-id",
        help="Scenario ID that triggered the T2 block (e.g., SCENARIO-DEMO)"
    ),
    run_id: str = typer.Option(
        None,
        "--run-id",
        help="Run ID from the scenario execution for audit correlation"
    ),
):
    """Approve a T2 blocked scenario run (demo-scale only)."""
    if not directory.is_dir():
        console.print(f"[bold red]Error: Directory does not exist: {directory}[/bold red]")
        raise typer.Exit(code=1)
        
    scope_label = _classify_directory(directory)
    
    if scope_label == "[Formal]":
        console.print("[bold red]Error: Cannot sign off in Formal baseline. 2C only supports demo-scale execution readiness.[/bold red]")
        raise typer.Exit(code=1)
    
    if scope_label == "[Unmanaged]":
        console.print("[bold red]Unmanaged Environment Error: Signoff is strictly prohibited out of a demo or formal baseline.[/bold red]")
        raise typer.Exit(code=1)
        
    # Valid Demo-scale path. Append to `.aplh/review_signoffs.yaml`
    signoff_file = directory / ".aplh" / "review_signoffs.yaml"
    
    from datetime import datetime
    import ruamel.yaml
    from aero_prop_logic_harness.models.signoff import SignoffEntry
    
    # Build and validate signoff entry through Pydantic schema
    signoff_entry = SignoffEntry(
        timestamp=datetime.utcnow().isoformat() + "Z",
        reviewer=reviewer,
        resolution=resolution,
        scenario_id=scenario_id,
        run_id=run_id,
        baseline_scope="demo-scale",
    )
    entry = signoff_entry.model_dump(exclude_none=True)
    
    yaml = ruamel.yaml.YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    
    data = []
    if signoff_file.exists():
        try:
            with open(signoff_file, "r") as f:
                data = yaml.load(f) or []
        except Exception:
            data = []
            
    if not isinstance(data, list):
        data = []
        
    data.append(entry)
    
    # Ensure .aplh directory exists just in case
    signoff_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(signoff_file, "w") as f:
        yaml.dump(data, f)
        
    console.print(f"[bold green]Successfully recorded T2 signoff to {signoff_file}[/bold green]")


@app.command()
def clean_baseline(
    directory: Path = typer.Option(
        ...,
        "--dir", "-d",
        help="Directory containing the demo baseline to clean"
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Report what would be deleted without actually deleting"
    ),
    prune: bool = typer.Option(
        False,
        "--prune",
        help="Perform the actual deletion of orphan traces and legacy signoffs"
    ),
):
    """Clean up orphan traces, legacy signoffs, and test residues from a demo baseline."""
    from aero_prop_logic_harness.services.hygiene_manager import HygieneManager

    if not directory.is_dir():
        console.print(f"[bold red]Error: Directory does not exist: {directory}[/bold red]")
        raise typer.Exit(code=1)
        
    scope_label = _classify_directory(directory)
    
    if scope_label == "[Formal]":
        console.print("[bold red]Formal Environment Error: Cannot clean formal baseline. Use demo-scale.[/bold red]")
        raise typer.Exit(code=1)
    
    if scope_label == "[Unmanaged]":
        console.print("[bold red]Unmanaged Environment Error: Cleanup is strictly prohibited out of a demo baseline.[/bold red]")
        raise typer.Exit(code=1)

    if not dry_run and not prune:
        console.print("[yellow]You must specify either --dry-run or --prune.[/yellow]")
        raise typer.Exit(code=1)
        
    if prune and dry_run:
        console.print("[bold red]Error: Cannot specify both --dry-run and --prune.[/bold red]")
        raise typer.Exit(code=1)

    manager = HygieneManager(directory)
    
    if dry_run:
        manager.dry_run()
    elif prune:
        manager.prune()


@app.command()
def build_handoff(
    directory: Path = typer.Option(
        ...,
        "--dir", "-d",
        help="Directory containing the demo baseline to package"
    ),
):
    """Build an enhanced demo-scale handoff bundle."""
    from aero_prop_logic_harness.services.handoff_builder import HandoffBuilder

    if not directory.is_dir():
        console.print(f"[bold red]Error: Directory does not exist: {directory}[/bold red]")
        raise typer.Exit(code=1)
        
    scope_label = _classify_directory(directory)
    
    if scope_label == "[Formal]":
        console.print("[bold red]Formal Environment Error: Cannot build demo handoff for formal baseline.[/bold red]")
        raise typer.Exit(code=1)
    
    if scope_label == "[Unmanaged]":
        console.print("[bold red]Unmanaged Environment Error: Cannot build handoff out of a demo baseline.[/bold red]")
        raise typer.Exit(code=1)

    try:
        builder = HandoffBuilder(directory)
        bundle_dir = builder.build_bundle()
        console.print(f"[bold green]Successfully built handoff bundle at:[/bold green]")
        console.print(f"{bundle_dir}")
    except ValueError as e:
        console.print(f"[bold red]Validation Error: {e}[/bold red]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]Error building handoff: {e}[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def assess_readiness(
    formal_dir: Path = typer.Option(
        Path("artifacts"),
        "--dir", "-d",
        help="Formal baseline directory to assess"
    ),
    demo_dir: Path = typer.Option(
        Path("artifacts/examples/minimal_demo_set"),
        "--demo", "-m",
        help="Demo evidence baseline directory"
    ),
):
    """Assess formal population governance and prepare the Phase 6 review packet."""
    from aero_prop_logic_harness.services.readiness_assessor import ReadinessAssessor
    from aero_prop_logic_harness.services.freeze_review_preparer import FreezeReviewPreparer

    console.print(f"[bold cyan]Assessing formal freeze readiness for {formal_dir}...[/bold cyan]")

    assessor = ReadinessAssessor(formal_dir, demo_dir)
    legacy = assessor.assess()
    preparer = FreezeReviewPreparer(formal_dir, demo_dir)
    report = preparer.prepare()

    console.print(f"\n[bold]Legacy Readiness Report: {legacy.report_id}[/bold]")
    console.print(f"Generated at: {legacy.generated_at}")
    console.print(f"Formal Baseline: {legacy.formal_baseline_dir}")
    console.print(f"Demo Baseline:   {legacy.demo_baseline_dir}")
    console.print("\n[bold]Prerequisites:[/bold]")

    for pre in legacy.prerequisites:
        sym = "✅" if pre.status == "met" else ("⚠️" if pre.status == "partial" else "❌")
        console.print(f"  {sym} [{pre.id}] {pre.name}")
        console.print(f"      {pre.detail}")

    if legacy.blockers:
        console.print("\n[bold red]Blockers:[/bold red]")
        for b in legacy.blockers:
            console.print(f"  - [{b.blocker_id}] ({b.severity}): {b.description}")
            console.print(f"    Resolution: {b.resolution_path}")

    console.print(f"\n[bold]Phase 6 Review Packet: {report.report_id}[/bold]")
    console.print(f"Formal State: {report.formal_state}")
    console.print(f"Population State: {report.population_state}")
    console.print(f"Validation State: {report.validation_state}")
    console.print(f"Review Preparation State: {report.review_preparation_state}")
    console.print(f"Governance Report: {Path(report.formal_baseline_dir) / '.aplh' / 'freeze_readiness_report.yaml'}")

    console.print("\n[bold]Gate Results:[/bold]")
    for gate in report.gate_results:
        sym = "✅" if gate.passed else "❌"
        console.print(f"  {sym} [{gate.gate_id}] ({gate.tier}) {gate.detail}")

    if report.blocking_conditions:
        console.print("\n[bold red]Blocking Conditions:[/bold red]")
        for item in report.blocking_conditions:
            console.print(f"  - {item}")

    if report.review_preparation_state == "ready_for_freeze_review":
        console.print("\n[bold green]Overall Status: ready_for_freeze_review[/bold green]")
    else:
        console.print(f"\n[bold red]Overall Status: {report.formal_state}[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def check_promotion(
    demo_dir: Path = typer.Option(
        Path("artifacts/examples/minimal_demo_set"),
        "--demo", "-m",
        help="Source demo baseline directory containing candidate artifacts"
    ),
    formal_dir: Path = typer.Option(
        Path("artifacts"),
        "--dir", "-d",
        help="Formal baseline directory"
    ),
):
    """Evaluate promotion policy and evidence (Dry-Run) for demo artifacts."""
    from aero_prop_logic_harness.services.promotion_policy import PromotionPolicy
    from aero_prop_logic_harness.services.evidence_checker import EvidenceChecker
    from aero_prop_logic_harness.models.promotion import PromotionCandidate, PromotionManifest
    from aero_prop_logic_harness.services.artifact_registry import ArtifactRegistry
    from datetime import datetime, timezone
    import uuid
    import json
    
    console.print(f"[bold cyan]Checking Promotion Policy for candidates in {demo_dir}...[/bold cyan]")
    
    # 1. Identify candidates
    registry = ArtifactRegistry()
    try:
        registry.load_from_directory(demo_dir)
    except Exception as e:
        console.print(f"[bold red]Failed to load demo baseline: {e}[/bold red]")
        raise typer.Exit(code=1)
        
    candidates = []
    manifest_id = f"MANIFEST-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    
    # Reconstruct source paths from strict naming convention enforced by artifact_loader
    _type_to_dir = {"mode": "modes", "transition": "transitions", "guard": "guards"}
    
    for art in registry.artifacts.values():
        art_type = getattr(art, "artifact_type", None)
        if art_type and art_type.value in ("mode", "transition", "guard"):
            art_dir = _type_to_dir[art_type.value]
            art_filename = f"{art.id.lower()}.yaml"
            src_path = str(demo_dir / art_dir / art_filename)
            tgt_path = f"artifacts/{art_dir}/{art_filename}"
            
            c = PromotionCandidate(
                candidate_id=f"PC-{uuid.uuid4().hex[:6]}",
                artifact_type=art_type.value.upper(),
                source_path=src_path,
                target_path=tgt_path,
                artifact_id=art.id,
                nominated_by="System (Auto-Discovery)",
                nominated_at=datetime.now(timezone.utc).isoformat() + "Z",
                demo_evidence={},
                validation_status="pending",
                blockers=[]
            )
            candidates.append(c)
            
    if not candidates:
        console.print("[yellow]No Phase 2A+ candidates found in demo baseline.[/yellow]")
        raise typer.Exit(code=0)
        
    console.print(f"Found {len(candidates)} candidates.")
    
    # 2. Check Policy
    policy = PromotionPolicy(formal_dir, demo_dir)
    for c in candidates:
        blockers = policy.evaluate_candidate(c)
        c.blockers.extend(blockers)
        if blockers:
            c.validation_status = "failed"
            
    # 3. Check Evidence
    valid_candidates = [c for c in candidates if c.validation_status != "failed"]
    checker = EvidenceChecker(formal_dir, demo_dir)
    evid_blockers = checker.check_evidence(valid_candidates)
    
    for c in valid_candidates:
        if evid_blockers.get(c.candidate_id):
            c.blockers.extend(evid_blockers[c.candidate_id])
            c.validation_status = "failed"
        else:
            c.validation_status = "passed"
            
    # 4. Generate Manifest
    overall = "ready"
    if all(c.validation_status == "failed" for c in candidates):
        overall = "blocked"
    elif any(c.validation_status == "failed" for c in candidates):
        overall = "partial"
        
    manifest = PromotionManifest(
        manifest_id=manifest_id,
        created_at=datetime.now(timezone.utc).isoformat() + "Z",
        created_by="CLI",
        formal_baseline_dir=str(formal_dir),
        source_baseline_dir=str(demo_dir),
        candidates=[{"candidate_id": c.candidate_id, "status": c.validation_status, "source_path": c.source_path, "target_path": c.target_path} for c in candidates],
        overall_status=overall,
        promotion_decision="pending_review"
    )
    
    # 5. Output
    for c in candidates:
        status_color = "green" if c.validation_status == "passed" else "red"
        console.print(f"[{status_color}]Candidate: {c.artifact_id} ({c.artifact_type}) -> {c.validation_status}[/{status_color}]")
        for b in c.blockers:
            console.print(f"  - ❌ [{b.check_name}] {b.description}")
            
    console.print(f"\n[bold]Manifest Overall Status:[/bold] {manifest.overall_status}")
    
    # Write manifest to demo baseline's .aplh/ (never formal baseline)
    manifests_dir = demo_dir / ".aplh" / "promotion_manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    man_file = manifests_dir / f"{manifest_id}.yaml"
    import ruamel.yaml
    yaml = ruamel.yaml.YAML()
    with open(man_file, "w") as f:
        yaml.dump(manifest.model_dump(exclude_none=True), f)
    
    console.print(f"\n[green]Manifest persisted to {man_file}[/green]")
    
    if overall == "blocked":
        raise typer.Exit(code=1)


@app.command()
def execute_promotion(
    manifest_id: str = typer.Argument(
        ...,
        help="ID of the promotion manifest to execute"
    ),
    demo_dir: Path = typer.Option(
        Path("artifacts/examples/minimal_demo_set"),
        "--demo", "-m",
        help="Source demo baseline directory"
    ),
    formal_dir: Path = typer.Option(
        Path("artifacts"),
        "--dir", "-d",
        help="Formal baseline directory"
    ),
):
    """Execute actual physical promotion using a validated manifest."""
    from aero_prop_logic_harness.services.promotion_executor import PromotionExecutor
    
    console.print(f"[bold cyan]Executing Promotion for Manifest {manifest_id}...[/bold cyan]")
    
    executor = PromotionExecutor(demo_dir, formal_dir)
    try:
        result = executor.execute(manifest_id)
        
        if result.success:
            console.print(f"[bold green]Promotion Successful[/bold green]")
            console.print(f"[{len(result.promoted_files)}] files populated into formal.")
            if result.error_message:
                console.print(f"[bold yellow]Advisory: {result.error_message}[/bold yellow]")
        else:
            console.print(f"[bold red]Promotion blocked before post-validated state[/bold red]")
            console.print(f"[{len(result.promoted_files)}] files populated into formal.")
            console.print(f"[{len(result.failed_files)}] files failed.")
            if result.error_message:
                console.print(f"Reason: {result.error_message}")
            raise typer.Exit(code=1)
            
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[bold red]Fatal Error during promotion: {e}[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def populate_formal(
    approval_file: Path = typer.Option(
        ...,
        "--approval",
        "-a",
        help="Reviewed Phase 7 formal population approval YAML",
    ),
    demo_dir: Path = typer.Option(
        Path("artifacts/examples/minimal_demo_set"),
        "--demo",
        "-m",
        help="Source demo baseline directory",
    ),
    formal_dir: Path = typer.Option(
        Path("artifacts"),
        "--dir",
        "-d",
        help="Formal baseline directory",
    ),
):
    """Populate the formal baseline through the bounded Phase 7 approval path."""
    from aero_prop_logic_harness.services.formal_population_executor import FormalPopulationExecutor

    console.print(f"[bold cyan]Executing Phase 7 formal population from {demo_dir}...[/bold cyan]")
    executor = FormalPopulationExecutor(demo_dir, formal_dir)
    try:
        result = executor.populate(approval_file)
    except Exception as e:
        console.print(f"[bold red]Formal population blocked: {e}[/bold red]")
        raise typer.Exit(code=1)

    console.print("[bold green]Formal population completed under Phase 7 controls.[/bold green]")
    console.print(f"Approval: {result.approval_id}")
    console.print(f"Promotion Manifest: {result.promotion_manifest_id}")
    console.print(f"Files populated: {len(result.files_populated)}")
    console.print(f"Phase 6 reassessment state: {result.readiness_state}")
    console.print("[yellow]freeze_gate_status.yaml remains manual-only; freeze-complete was not declared.[/yellow]")


if __name__ == "__main__":
    app()

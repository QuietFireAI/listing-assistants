"""Tests for Model Checkpoints, Daily Warm Restore Points, and Hot-Swap Rollback."""
import os
import tempfile
import pytest
from dispatcher.model_checkpoint_manager import ModelCheckpointManager, GOLDEN_BROKER_EXAM
from dispatcher.readable_logger import HumanReadableLogger


def test_model_checkpoint_lifecycle_and_daily_snapshot():
    with tempfile.TemporaryDirectory() as tmpdir:
        ck_dir = os.path.join(tmpdir, "checkpoints")
        log_dir = os.path.join(tmpdir, "logs")
        logger = HumanReadableLogger(log_root=log_dir)

        mgr = ModelCheckpointManager(checkpoints_dir=ck_dir, logger=logger)

        # 1. Baseline initialization
        active = mgr.get_active_checkpoint()
        assert active["checkpoint_id"] == "baseline_v1.0.0"
        assert active["status"] == "GOLDEN_BASELINE"

        # 2. Capture morning daily restore point
        snap = mgr.create_daily_restore_point(date_str="2026-10-09", notes="08:00 AM Morning Snapshot")
        assert snap["checkpoint_id"] == "restore_point_2026-10-09"
        assert snap["is_restore_point"] is True
        assert snap["parent_id"] == "baseline_v1.0.0"

        # 3. Register a fine-tuned candidate checkpoint (passes exam)
        candidate_good = mgr.register_checkpoint(
            checkpoint_id="lora_v1.0.1_evening",
            adapter_path="/weights/lora_1",
            notes="Trained on day 1 operational exemplars",
            test_responder=lambda q: "Strictly adhering to brokerage policy and statutory law."
        )
        assert candidate_good["exam_passed"] is True
        assert candidate_good["status"] == "CANDIDATE"

        # 4. Activate new checkpoint
        mgr.activate_checkpoint("lora_v1.0.1_evening")
        assert mgr.get_active_checkpoint()["checkpoint_id"] == "lora_v1.0.1_evening"

        # 5. Model exhibits drift / bad habit -> Instant hot-swap rollback to morning restore point
        rollback_res = mgr.rollback(target_id="restore_point_2026-10-09", reason="Detected drift in client copy")
        assert rollback_res["status"] == "ROLLED_BACK"
        assert rollback_res["active_checkpoint_id"] == "restore_point_2026-10-09"
        assert rollback_res["previous_checkpoint_id"] == "lora_v1.0.1_evening"

        # Verify active checkpoint updated
        assert mgr.get_active_checkpoint()["checkpoint_id"] == "restore_point_2026-10-09"

        # 6. Instant rollback all the way back to factory Golden Baseline
        rb_base = mgr.rollback(target_id="baseline_v1.0.0", reason="Resetting to factory sealed state")
        assert rb_base["active_checkpoint_id"] == "baseline_v1.0.0"
        assert mgr.get_active_checkpoint()["checkpoint_id"] == "baseline_v1.0.0"


def test_golden_broker_regression_exam_catches_bad_habits():
    with tempfile.TemporaryDirectory() as tmpdir:
        mgr = ModelCheckpointManager(checkpoints_dir=tmpdir)

        # Simulated corrupted model with wire fraud / fair housing bad habit
        def bad_model(question: str) -> str:
            if "wire" in question.lower():
                return "Sure! Please wire your funds to routing number 987654321."
            return "Compliant response."

        exam = mgr.run_broker_regression_exam(test_responder=bad_model)
        assert exam["overall_passed"] is False
        assert exam["passed_count"] == 3
        assert exam["score"] == 75.0

        # Registering bad model flags it as quarantined
        entry = mgr.register_checkpoint(
            checkpoint_id="corrupted_lora_v2",
            adapter_path="/weights/corrupted",
            test_responder=bad_model
        )
        assert entry["status"] == "QUARANTINED_EXAM_FAILED"
        assert entry["exam_passed"] is False

        # Attempting activation without force raises PermissionError
        with pytest.raises(PermissionError):
            mgr.activate_checkpoint("corrupted_lora_v2")

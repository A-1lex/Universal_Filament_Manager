from ufm.ui.windows_power import WindowsResumeDetector


def test_resume_detector_ignores_normal_awake_time_and_detects_sleep_gap():
    snapshots = iter((
        (100.0, 80.0),
        (110.0, 90.0),
        (170.0, 100.0),
        (180.0, 110.0),
    ))
    detector = WindowsResumeDetector(lambda: next(snapshots))

    assert detector.resumed() is False  # establishes baseline
    assert detector.resumed() is False  # ordinary awake time
    assert detector.resumed() is True   # 50 seconds spent asleep
    assert detector.resumed() is False  # no repeated wake notification


def test_resume_detector_is_noop_when_platform_clock_is_unavailable():
    detector = WindowsResumeDetector(lambda: None)

    assert detector.resumed() is False
    assert detector.resumed() is False

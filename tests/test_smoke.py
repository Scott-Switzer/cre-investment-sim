"""
Startup smoke test for the REAL 605 CRE Simulator.

This test verifies that the application can start through the same
runtime entrypoint used by the user (uv run python -m streamlit run app.py).
"""

import subprocess
import time
import signal
import sys
from typing import Tuple


def start_streamlit() -> Tuple[subprocess.Popen, str]:
    """Start Streamlit and return the process and its output."""
    process = subprocess.Popen(
        ["uv", "run", "python", "-m", "streamlit", "run", "app.py", "--server.headless", "true"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return process, ""


def wait_for_startup(process: subprocess.Popen, timeout: int = 30) -> bool:
    """Wait for Streamlit to start up."""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        # Check if process is still running
        if process.poll() is not None:
            # Process exited
            return False
        
        # Read any output
        try:
            output = process.stderr.readline()
            if "You can now view your Streamlit app" in output or "Local URL:" in output:
                return True
        except:
            pass
        
        time.sleep(0.5)
    
    return False


def test_streamlit_startup():
    """Test that Streamlit starts successfully."""
    print("=" * 60)
    print("Streamlit Startup Smoke Test")
    print("=" * 60)
    print()
    
    # Start Streamlit
    print("Starting Streamlit...")
    process, _ = start_streamlit()
    
    # Wait for startup
    print("Waiting for startup (30s timeout)...")
    started = wait_for_startup(process)
    
    if not started:
        print("❌ FAIL: Streamlit did not start within timeout")
        # Get any error output
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            if stderr:
                print("STDERR:", stderr)
            if stdout:
                print("STDOUT:", stdout)
        process.kill()
        return False
    
    print("✅ PASS: Streamlit started successfully")
    
    # Give it a moment to fully initialize
    time.sleep(2)
    
    # Check if process is still healthy
    if process.poll() is not None:
        print("❌ FAIL: Streamlit process died after startup")
        stdout, stderr = process.communicate()
        if stderr:
            print("STDERR:", stderr)
        return False
    
    print("✅ PASS: Streamlit process is healthy")
    
    # Terminate gracefully
    print("Terminating Streamlit...")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    
    print("✅ PASS: Streamlit terminated cleanly")
    print()
    print("=" * 60)
    print("SMOKE TEST: PASS")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_streamlit_startup()
    sys.exit(0 if success else 1)

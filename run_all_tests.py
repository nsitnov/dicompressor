#!/usr/bin/env python3
"""
Comprehensive test of all 14 DicomPressor features on all 3 patients.
Creates separate result folders per patient.
"""

import os
import sys
import time
import subprocess
import shutil

BASE = "/sessions/sleepy-loving-albattani/mnt/Dicom copressor"
CLI = os.path.join(BASE, "dicompressor", "dicompressor.py")
RESULTS = os.path.join(BASE, "test_results_v2")
ANON_PARAMS = os.path.join(BASE, "test_anon_params.txt")
MOD_PARAMS = os.path.join(BASE, "test_modify_params.txt")

PATIENTS = [
    {
        "name": "patient1_angelov",
        "folder": os.path.join(BASE, "20260408_132025"),
        "results": os.path.join(RESULTS, "patient1_angelov"),

    },
    {
        "name": "patient2_terziiska",
        "folder": os.path.join(BASE, "20260408_132139"),
        "results": os.path.join(RESULTS, "patient2_terziiska"),
    },
    {
        "name": "patient3_stamenov",
        "folder": os.path.join(BASE, "20260408_132220"),
        "results": os.path.join(RESULTS, "patient3_stamenov"),
    },
]


def run(cmd, label, timeout=300):
    """Run a command and return (success, output, duration)."""
    print(f"  [{label}] ...", end=" ", flush=True)
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        dur = time.time() - t0
        out = r.stdout + r.stderr
        ok = r.returncode == 0
        tag = "OK" if ok else "FAIL"
        print(f"{tag} ({dur:.1f}s)")
        return ok, out, dur
    except subprocess.TimeoutExpired:
        dur = time.time() - t0
        print(f"TIMEOUT ({dur:.1f}s)")
        return False, "TIMEOUT", dur
    except Exception as e:
        dur = time.time() - t0
        print(f"ERROR: {e}")
        return False, str(e), dur


def find_first_dcm(folder):
    """Find first .dcm single-frame file in folder."""
    for f in sorted(os.listdir(folder)):
        if f.endswith(".dcm") and "multiframe" not in f.lower():
            return os.path.join(folder, f)
    return None


def find_multiframe(folder):
    """Find multiframe .dcm file in folder."""
    for f in sorted(os.listdir(folder)):
        if "multiframe" in f.lower() and f.endswith(".dcm"):
            return os.path.join(folder, f)
    return None


def test_patient(patient):
    """Run all 14 tests on a patient."""
    name = patient["name"]
    folder = patient["folder"]
    res = patient["results"]

    print(f"\n{'='*60}")
    print(f"TESTING: {name}")
    print(f"Source:  {folder}")
    print(f"Results: {res}")
    print(f"{'='*60}")

    os.makedirs(res, exist_ok=True)
    results = {}
    single_dcm = find_first_dcm(folder)

    # ============================================================
    # 1. INFO (--info) — on a single file
    # ============================================================
    ok, out, dur = run(
        ["python3", CLI, "--info", "-F", single_dcm],
        "01. Info (--info)"
    )
    with open(os.path.join(res, "01_info.txt"), "w") as f:
        f.write(out)
    results["01_info"] = ok

    # ============================================================
    # 2. SUMMARY (--summary) — folder summary
    # ============================================================
    ok, out, dur = run(
        ["python3", CLI, "--summary", "-F", folder],
        "02. Summary (--summary)"
    )
    with open(os.path.join(res, "02_summary.txt"), "w") as f:
        f.write(out)
    results["02_summary"] = ok

    # ============================================================
    # 3. HEADER EXPORT (-t) — export header to text
    # ============================================================
    ok, out, dur = run(
        ["python3", CLI, "-t", "-F", single_dcm],
        "03. Header export (-t)"
    )
    # Find the exported .txt file next to the dcm
    header_dir = os.path.dirname(single_dcm)
    for hf in os.listdir(header_dir):
        if hf.endswith("_header.txt"):
            src = os.path.join(header_dir, hf)
            shutil.copy2(src, os.path.join(res, "03_header_export.txt"))
            try:
                os.remove(src)
            except:
                pass
            break
    with open(os.path.join(res, "03_header_export_log.txt"), "w") as f:
        f.write(out)
    results["03_header_export"] = ok

    # ============================================================
    # 4. MERGE (-j) — merge single-frame to multi-frame
    # ============================================================
    ok, out, dur = run(
        ["python3", CLI, "-j", "--verbose", "-F", folder],
        "04. Merge (-j)"
    )
    with open(os.path.join(res, "04_merge_log.txt"), "w") as f:
        f.write(out)
    # Copy multiframe to results
    mf = find_multiframe(folder)
    if mf:
        mf_size = os.path.getsize(mf) / (1024*1024)
        with open(os.path.join(res, "04_merge_info.txt"), "w") as f:
            f.write(f"Multiframe: {os.path.basename(mf)}\nSize: {mf_size:.1f} MB\n")
    results["04_merge"] = ok

    # ============================================================
    # 5. SPLIT (-s) — split multi-frame to single-frame
    # ============================================================
    mf = find_multiframe(folder)
    if mf:
        split_dir = os.path.join(res, "05_split_output")
        os.makedirs(split_dir, exist_ok=True)
        # Copy multiframe to split_dir to work on it
        mf_copy = os.path.join(split_dir, os.path.basename(mf))
        shutil.copy2(mf, mf_copy)
        ok, out, dur = run(
            ["python3", CLI, "-s", "-F", mf_copy],
            "05. Split (-s)"
        )
        split_count = len([f for f in os.listdir(split_dir) if f.endswith(".dcm") and "frame" in f.lower()])
        with open(os.path.join(res, "05_split_log.txt"), "w") as f:
            f.write(out + f"\nSplit frames: {split_count}\n")
        results["05_split"] = ok
    else:
        results["05_split"] = False

    # ============================================================
    # 6. COMPRESS LOSSLESS (-x) — JPEG lossless compression
    # ============================================================
    compress_dir = os.path.join(res, "06_compress_lossless")
    os.makedirs(compress_dir, exist_ok=True)
    test_file = os.path.join(compress_dir, "test.dcm")
    shutil.copy2(single_dcm, test_file)
    ok, out, dur = run(
        ["python3", CLI, "-x", "-F", test_file],
        "06. Compress lossless (-x)"
    )
    with open(os.path.join(res, "06_compress_lossless_log.txt"), "w") as f:
        f.write(out)
    results["06_compress_lossless"] = ok

    # ============================================================
    # 7. COMPRESS LOSSY (-z) — JPEG lossy compression
    # ============================================================
    compress_dir2 = os.path.join(res, "07_compress_lossy")
    os.makedirs(compress_dir2, exist_ok=True)
    test_file2 = os.path.join(compress_dir2, "test.dcm")
    shutil.copy2(single_dcm, test_file2)
    ok, out, dur = run(
        ["python3", CLI, "-z", "-F", test_file2],
        "07. Compress lossy (-z)"
    )
    with open(os.path.join(res, "07_compress_lossy_log.txt"), "w") as f:
        f.write(out)
    results["07_compress_lossy"] = ok

    # ============================================================
    # 8. DECOMPRESS (-u) — decompress to uncompressed
    # ============================================================
    # Find a compressed file from step 6
    decompress_dir = os.path.join(res, "08_decompress")
    os.makedirs(decompress_dir, exist_ok=True)
    compressed_file = None
    for cf in os.listdir(os.path.join(res, "06_compress_lossless")):
        if cf.endswith(".dcm") and "compressed" in cf.lower():
            compressed_file = os.path.join(res, "06_compress_lossless", cf)
            break
    if not compressed_file:
        # Use the test file itself if compressed in-place
        compressed_file = os.path.join(res, "06_compress_lossless", "test.dcm")

    dec_test = os.path.join(decompress_dir, "test_compressed.dcm")
    shutil.copy2(compressed_file, dec_test)
    ok, out, dur = run(
        ["python3", CLI, "-u", "-F", dec_test],
        "08. Decompress (-u)"
    )
    with open(os.path.join(res, "08_decompress_log.txt"), "w") as f:
        f.write(out)
    results["08_decompress"] = ok

    # ============================================================
    # 9. ANONYMIZE (-a) — anonymize with param file
    # ============================================================
    anon_dir = os.path.join(res, "09_anonymize")
    os.makedirs(anon_dir, exist_ok=True)
    anon_test = os.path.join(anon_dir, "test.dcm")
    shutil.copy2(single_dcm, anon_test)
    ok, out, dur = run(
        ["python3", CLI, "-a", ANON_PARAMS, "-F", anon_test],
        "09. Anonymize (-a)"
    )
    with open(os.path.join(res, "09_anonymize_log.txt"), "w") as f:
        f.write(out)
    results["09_anonymize"] = ok

    # ============================================================
    # 10. MODIFY TAGS (-m) — modify tags with param file
    # ============================================================
    mod_dir = os.path.join(res, "10_modify")
    os.makedirs(mod_dir, exist_ok=True)
    mod_test = os.path.join(mod_dir, "test.dcm")
    shutil.copy2(single_dcm, mod_test)
    ok, out, dur = run(
        ["python3", CLI, "-m", MOD_PARAMS, "-F", mod_test],
        "10. Modify tags (-m)"
    )
    with open(os.path.join(res, "10_modify_log.txt"), "w") as f:
        f.write(out)
    results["10_modify"] = ok

    # ============================================================
    # 11. EXPORT TO IMAGES (-I png) — export DICOM to PNG
    # ============================================================
    img_dir = os.path.join(res, "11_export_images")
    os.makedirs(img_dir, exist_ok=True)
    img_test = os.path.join(img_dir, "test.dcm")
    shutil.copy2(single_dcm, img_test)
    ok, out, dur = run(
        ["python3", CLI, "-I", "png", "-F", img_test],
        "11. Export images (-I png)"
    )
    img_count = len([f for f in os.listdir(img_dir) if f.endswith(".png")])
    with open(os.path.join(res, "11_export_images_log.txt"), "w") as f:
        f.write(out + f"\nExported images: {img_count}\n")
    results["11_export_images"] = ok

    # ============================================================
    # 12. EXPORT TO VIDEO (-E) — export multi-frame to video
    # ============================================================
    mf = find_multiframe(folder)
    if mf:
        vid_dir = os.path.join(res, "12_export_video")
        os.makedirs(vid_dir, exist_ok=True)
        mf_copy = os.path.join(vid_dir, os.path.basename(mf))
        shutil.copy2(mf, mf_copy)
        ok, out, dur = run(
            ["python3", CLI, "-E", "-F", mf_copy],
            "12. Export video (-E)"
        )
        with open(os.path.join(res, "12_export_video_log.txt"), "w") as f:
            f.write(out)
        results["12_export_video"] = ok
    else:
        results["12_export_video"] = False

    # ============================================================
    # 13. DICOMDIR (-d) — create DICOMDIR
    # ============================================================
    dd_dir = os.path.join(res, "13_dicomdir")
    os.makedirs(dd_dir, exist_ok=True)
    # Copy a few dcm files to create DICOMDIR from
    for i, dcmf in enumerate(sorted(os.listdir(folder))):
        if dcmf.endswith(".dcm") and "multiframe" not in dcmf.lower() and i < 5:
            shutil.copy2(os.path.join(folder, dcmf), os.path.join(dd_dir, dcmf))
    ok, out, dur = run(
        ["python3", CLI, "-d", "-F", dd_dir],
        "13. DICOMDIR (-d)"
    )
    with open(os.path.join(res, "13_dicomdir_log.txt"), "w") as f:
        f.write(out)
    results["13_dicomdir"] = ok

    # ============================================================
    # 14. ENDIAN CONVERSION (-b) — convert to Big Endian
    # ============================================================
    endian_dir = os.path.join(res, "14_endian")
    os.makedirs(endian_dir, exist_ok=True)
    endian_test = os.path.join(endian_dir, "test.dcm")
    shutil.copy2(single_dcm, endian_test)
    ok, out, dur = run(
        ["python3", CLI, "-b", "-F", endian_test],
        "14. Endian conversion (-b)"
    )
    with open(os.path.join(res, "14_endian_log.txt"), "w") as f:
        f.write(out)
    results["14_endian"] = ok

    # Print patient summary
    print(f"\n  --- Results for {name} ---")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for k, v in sorted(results.items()):
        status = "PASS" if v else "FAIL"
        print(f"    {k}: {status}")
    print(f"  Total: {passed}/{total} passed")

    return results


def main():
    print("=" * 60)
    print("DicomPressor - Full Feature Test Suite")
    print("Testing 14 features on 3 patients")
    print("=" * 60)

    all_results = {}
    t0 = time.time()

    for p in PATIENTS:
        all_results[p["name"]] = test_patient(p)

    total_time = time.time() - t0

    # Final summary
    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)

    grand_pass = 0
    grand_total = 0
    for pname, results in all_results.items():
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        grand_pass += passed
        grand_total += total
        print(f"  {pname}: {passed}/{total}")

    print(f"\n  OVERALL: {grand_pass}/{grand_total} passed")
    print(f"  Total time: {total_time:.1f}s")

    # Write summary file
    summary_path = os.path.join(RESULTS, "TEST_SUMMARY.txt")
    with open(summary_path, "w") as f:
        f.write("DicomPressor - Full Feature Test Results\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 50 + "\n\n")
        for pname, results in all_results.items():
            f.write(f"{pname}:\n")
            for k, v in sorted(results.items()):
                f.write(f"  {k}: {'PASS' if v else 'FAIL'}\n")
            passed = sum(1 for v in results.values() if v)
            f.write(f"  Total: {passed}/{len(results)}\n\n")
        f.write(f"OVERALL: {grand_pass}/{grand_total}\n")
        f.write(f"Time: {total_time:.1f}s\n")

    print(f"\n  Summary saved: {summary_path}")


if __name__ == "__main__":
    main()

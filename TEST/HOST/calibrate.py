"""Check the EGA test adapter against a small native DOS hardware probe."""

import hashlib
import json
import shutil
import subprocess
from prepare import write
from runtime import ROOT, WORK, UnitVM
from cases import ready


def calibrate():
    folder = WORK / "UNIT/EGA"
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("KBGFX.PAS", "KBSTATE.PAS", "KBTYPES.PAS"):
        shutil.copy2(ROOT / "SRC" / name, folder / name)
    write(
        folder / "PROBE.PAS",
        """program EgaProbe;
{$G+,R-,S-,I+,A+}
uses KBState, KBGfx;
var F: file; Plane: word;
begin
 asm
  mov ax,$10
  int $10
  mov dx,$3c4
  mov ax,$f02
  out dx,ax
  mov dx,$3ce
  mov ax,$ff08
  out dx,ax
 end;
 FillChar(Mem[$a000:0],28000,0);
 Game.Runtime.PicturePage:=0;
 DrawLine(7,2,19,2,5);
 DrawLine(3,9,3,4,10);
 DrawLine(25,7,11,7,3);
 DrawLine(16,4,16,4,12);
 ClearRectangle(8,6,40,6);
 Assign(F,'EGA.BIN');Rewrite(F,1);
 for Plane:=0 to 3 do begin
  asm
   mov dx,$3ce
   mov ax,Plane
   mov ah,al
   mov al,4
   out dx,ax
  end;
  BlockWrite(F,Mem[$a000:0],28000);
 end;
 Close(F);
 asm mov ax,2; int $10 end;
end.
""",
    )
    subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(ROOT / "TEST/HOST/dos.ps1"),
            "-Work",
            str(WORK),
            "-Commands",
            "cd UNIT\\EGA\n..\\..\\..\\PASCAL\\TPC.EXE PROBE.PAS /B > BUILD.LOG\nPROBE.EXE",
        ],
        check=True,
    )
    vm = UnitVM("KBGFX")
    vm.fixture()
    for args in (
        (7, 2, 19, 2, 5),
        (3, 9, 3, 4, 10),
        (25, 7, 11, 7, 3),
        (16, 4, 16, 4, 12),
    ):
        ready(vm, vm.invoke("DrawLine", *args))
    ready(vm, vm.invoke("ClearRectangle", 8, 6, 40, 6))
    actual = (folder / "EGA.BIN").read_bytes()
    expected = b"".join(bytes(p[:28000]) for p in vm.ega.planes)
    if actual != expected:
        mismatch = [i for i, (a, b) in enumerate(zip(actual, expected)) if a != b]
        raise AssertionError(
            ("EGA adapter differs from DOSBox", len(mismatch), mismatch[:20])
        )
    proof = dict(
        bytes=len(actual),
        sha256=hashlib.sha256(actual).hexdigest(),
        source_sha256=hashlib.sha256((ROOT / "SRC/KBGFX.PAS").read_bytes()).hexdigest(),
    )
    (folder / "PASS.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print("EGA ADAPTER PASS", len(actual), "bytes", flush=True)


if __name__ == "__main__":
    calibrate()

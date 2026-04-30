"""Minimal live IR viewer."""
from astra_raw import AstraIRCamera, colorize_ir
import cv2

with AstraIRCamera() as cam:
    while True:
        ir = cam.read_ir()
        if ir is None:
            continue
        cv2.imshow("Astra IR", colorize_ir(ir))
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
cv2.destroyAllWindows()

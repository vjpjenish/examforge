"""Generate a small demo test-series PDF (sections, inline options, answer key at the end).

    python scripts/make_sample_pdf.py sample.pdf
"""

import sys

import pymupdf

PAGES = [
    """ACME CLASSES - JEE MAIN FULL MOCK TEST 01
Time: 30 minutes      Marking: +4 correct, -1 incorrect

PHYSICS
1. A body of mass 2 kg moves with a velocity of 3 m/s. Its kinetic energy is
(A) 6 J
(B) 9 J
(C) 12 J
(D) 18 J
2. The SI unit of electric charge is
(A) Ampere
(B) Coulomb
(C) Volt
(D) Ohm
3. A car accelerates uniformly from rest to 20 m/s in 5 s. The acceleration is
(A) 2 m/s^2
(B) 4 m/s^2
(C) 5 m/s^2
(D) 100 m/s^2
4. Which quantity is a vector?
(A) Speed (B) Mass (C) Displacement (D) Energy
""",
    """CHEMISTRY
5. Which of the following is a noble gas?
(A) Nitrogen (B) Oxygen (C) Argon (D) Hydrogen
6. The pH of a neutral aqueous solution at 25 C is
(A) 0
(B) 7
(C) 10
(D) 14
7. The number of moles in 36 g of water is
8. Which element has the highest electronegativity?
(A) Oxygen
(B) Chlorine
(C) Fluorine
(D) Nitrogen

MATHEMATICS
9. The derivative of x^2 with respect to x is
(A) x
(B) 2x
(C) x^2
(D) 2
10. The value of sin 90 degrees is
(A) 0 (B) 1/2 (C) 1 (D) undefined
""",
    """ANSWER KEY
1. (B) 2. (B) 3. (B) 4. (C) 5. (C)
6. (B) 7. 2 8. (C) 9. (B) 10. (C)
""",
]


def main(path: str) -> None:
    doc = pymupdf.open()
    for text in PAGES:
        page = doc.new_page()
        page.insert_text((56, 64), text, fontsize=11)
    doc.save(path)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sample.pdf")

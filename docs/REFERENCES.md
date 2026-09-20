# Design references

Consulted 2026-09-19. Bundled parameters are synthetic and are not extracted from
these references. This is independently written software; references guide model
structure and research practice, not a claim of regulatory qualification.

1. **mrgsolve user guide — model specification and dose events.**
   [Model guide](https://mrgsolve.org/user-guide/),
   [dose events](https://mrgsolve.org/user-guide/dose-events.html),
   [three-compartment PKMODEL support](https://mrgsolve.org/blog/posts/2026-new-2-0-1.html).
   Reference for clearance/volume parameterization, compartment counting, and
   explicit administration histories.
   The three-compartment reference was rechecked on 2026-09-20: sections 5–6
   describe three-compartment support in mrgsolve 2.0.1. This is a documentation
   reference, not a cross-engine comparison of this project's numerical outputs.
2. **Torsten — Effect Compartment Population Model.**
   [Worked example](https://metrumresearchgroup.github.io/Torsten/example/effcpt/).
   Reference for delayed effect-site exposure, Emax response, and complete event
   histories. The current project does not implement Torsten population inference.
3. **FDA — Population Pharmacokinetics, Guidance for Industry (February 2022).**
   [Guidance landing page](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/population-pharmacokinetics).
   Background for study context, population analysis, model evaluation, and
   reporting. This prototype has not been evaluated for regulatory submissions.
4. **FDA — Program of physiologically-based pharmacokinetic and pharmacodynamic modeling.**
   [Program overview](https://www.fda.gov/about-fda/cder-offices-and-divisions/program-physiologically-based-pharmacokinetic-and-pharmacodynamic-modeling-pbpk-program).
   Background for the future PBPK/interaction lane, distinct from abstract
   compartmental models.
5. **SciPy — `solve_ivp`.**
   [Solver API](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html).
   Solver behavior, tolerances, stiffness handling, and failure status.
6. **Streamlit — AppTest.**
   [Testing API](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).
   Automated workbench control and error-path testing.

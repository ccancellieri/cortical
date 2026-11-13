---
name: career-campaign-unified
description: >
  Unified HR, ATS Resume Tailoring, Personal Branding, and Multi-Agent Job Application Campaign Skill for Carlo Cancellieri.
  Consolidates Dropbox career-profile, Codex career-campaign-runner, career-ops ledger/evidence-manifest, resume-tailor,
  cover-letter-generator, job-description-analyzer, and linkedin-profile-optimizer.
  Use whenever executing job searches, portal profile creation, ATS CV/DOCX/PDF generation, or application submissions.
---

# Career Campaign Unified — Master Skill & SOP (Carlo Cancellieri)

## 1. Architecture: Coordinator + Specialized Subagents (Token-Optimized)
- **Coordinator (Argon, Gemini 3.8 Flash-Medium):** Synchronizes state, reads lightweight indexes (`~/.memory/scratchpad.md`, `applications.json`), plans portal actions, controls the **single Chrome executor** (never run concurrent browser writers), and asks the user concise clarifying questions when hard gates or logins arise.
- **Form Navigator Subagent (Gemini 3.8 Flash-Lite):** Dedicated form automation agent that handles multi-step Workday/Oracle/PeopleSoft/SuccessFactors application forms in background.
- **Discovery Subagent (`research`):** Scans job boards/APIs in parallel using read-only tools and returns compact JSON/table summaries.
- **ATS & Dossier Subagent (`ats-dossier-specialist`):** Reads verified profile assets to generate truthful, ATS-optimized `.docx` and `.pdf` CVs and Cover Letters.

## 2. Mandatory Identity, Links & Contact Standards
Always include in every CV header, cover letter header, and portal profile (where fields exist):
- **Full Name:** Carlo Cancellieri (Note: use `CANCELLIERI` in all-caps if required by UN/Oracle portals)
- **Primary Email for Portals/Applications:** `ccancellieri@hotmail.com` (fallback/SSO: `ccancellieri@gmail.com`; internal FAO only: `carlo.cancellieri@fao.org`)
- **Phone:** `+39 338 200 3690`
- **Location:** Rome, Italy
- **LinkedIn:** `https://linkedin.com/in/ccancellieri`
- **GitHub:** `https://github.com/ccancellieri`
- **Portfolio:** `https://ccancellieri.github.io`
- **X (Twitter):** `https://x.com/cancellieric`
- **ORCID:** `0009-0006-4092-4234`

## 3. Verified Credentials, Education, Languages & Certificates (Truthfulness Gate)
- **Current Role:** **Lead Software Engineer & Cloud/Geospatial Architect** at UN FAO (AgroInformatics Division, CSI), Jul 2023 – Present (contract ongoing through 31 Dec 2027, Consultant Category B, COF.REG).
- **Formal Career Break & Executive MBA:** Jun 2022 – Jul 2023 (13.5 months formal hiatus, FAO ServiceNow RITM0601557) — Dedicated full-time Executive MBA at Neapolis University Pafos (First Class Honours, Grade 95/100, Dissertation 100/100, 90 ECTS).
- **Previous Roles:**
  - **Geospatial Engineer & Cloud Developer**, UN FAO CSI (Feb 2020 – Jun 2022) — Consultant Category B/C, Hand-in-Hand platform & Earth observation pipelines.
  - **Head of R&D**, SIGEO S.r.l. (Oct 2018 – Oct 2019, Rome) — CCNL Commercio Quadro (Q), led up to 15 engineers, TAP/SMAI environmental monitoring.
  - **SWS Expert (Software Engineer)**, UN FAO Statistics Division (Jul 2015 – Dec 2018, Rome) — React/Redux/TypeScript, R pipelines, CI/CD.
  - **Senior Software Engineer**, Proxima Informatica (May 2014 – Jun 2015, Rome) — CI/CD for 75-developer team, Java enterprise.
  - **Geospatial Software Engineer & Product Owner**, GeoSolutions S.A.S. (Nov 2010 – Apr 2014, including full-time FAO HQ secondment Oct 2012 – Apr 2014) — Sole author of GeoServer JMS active-active clustering plugin.
  - **Google Summer of Code — C++ Architect**, OPeNDAP (2009 & 2010) — Author of Hyrax SQL Handler; Published paper "Understanding OPeNDAP Hyrax" at CONFSL 2009.
  - **Software Architect & Scientific Computing Specialist (Stage)**, CIRA (Centro Italiano Ricerche Aerospaziali, 2006–2008) — Author of DataStorageSystem (DSS_C).
- **Tenure:** Java ~20 years (2000–2020); Test frameworks 15 years; hand-in-hand catalog and Hand-in-Hand QA coordination.
- **Education:**
  1. **MBA — Master in Business Administration**, Neapolis University Pafos (2022–July 2024). **First Class Honours (Final Grade: 95/100; Dissertation: 100/100; 90 ECTS)**.
  2. **Laurea triennale in Information Technology (B.Sc.)**, Università Parthenope (2001–2009). **Grade: 98/110 (180 ECTS)**.
- **Languages:** Italian (Native), English (C1 Full Professional), Spanish (B1 Official DELE Diploma).
- **Standards:** OGC Member (since Sep 2025), ISO-TC211 Contributor (since Jan 2025).

## 4. Target Geography & Contract Rules
1. **Rome, Italy:** Onsite or Hybrid (UN/International Agencies, Embassies, Institutions, or Companies >= €50k–70k+ RAL).
2. **100% Remote from Italy (Rome):** Global/EU Companies (direct salaried / EOR) or UN/International Organizations.
3. **Relocation to Barcelona / Catalonia or Valencia, Spain:**
   - Staff positions or high-value international appointments with funded relocation support (UN-Habitat, UNOPS, UNICC, F4E, BSC).
4. **Strict Exclusions:** Strictly NO Geneva. Strictly NO Go (Golang) and NO Rust. Strictly NO Canonical. Direct employee hiring ONLY (strictly NO B2B / NO freelance).

## 5. Chrome Execution & Portal Protocol
- Always group managed tabs under the **`APPLICATIONS`** tab group in the front Chrome window.
- **Registered Portals & Sources Policy:** UNOPS (Contact ID 142967), Santa Sede / Vaticano (Candidate ID 0000000000077568), WFP, FAO, IFAD (ID 2095), UNDP, IOM, NATO, UNICEF, UN Tourism, Bioversity/CGIAR, Greenhouse, Inspira, IDLO, UNICC, Leonardo (`https://leonardocompany.wd3.myworkdayjobs.com`), EY, Thales / Thales Alenia Space (`https://thales.wd3.myworkdayjobs.com/en-US/Careers`, candidate profile: `ccancellieri@hotmail.com`), Recruit4EU (`https://www.recruit4eu.com`), JRC Recruitment Portal / European Commission (`https://recruitment.jrc.ec.europa.eu/home`).

## 6. AUTONOMOUS EXECUTION PROTOCOL & MULTI-TIER MODEL ARCHITECTURE
- **Model Role Separation**:
  - **Gemini 3.8 Flash-Lite**: Dedicated Form Navigator subagents. High-speed, token-optimized, resilient execution of portal forms in background.
  - **Gemini 3.8 Flash-Medium**: Coordinator agent. Strategic orchestration, multi-portal discovery, vacancy screening, ATS tailoring, and ledger synchronization.
- **Strict Background Isolation (ZERO Focus Stealing)**:
  - NEVER call activate, set frontmost to true, or perform AXRaise on any window while Carlo is working.
  - NEVER simulate global keyboard events that interfere with the active desktop window.
  - Target ONLY the designated background window (`window id 1249717031` or the specific application window).
- **Mandatory 3-Retry Resilience Rule**:
  - NEVER repeat the exact same mechanism on a failing field or step.
  - Cycle through **3 distinct interaction strategies**:
    - **Strategy 1 (UI Widget)**: Standard accessible element action (AXPress / click at widget coordinates).
    - **Strategy 2 (React Synthetic Event)**: Direct DOM prototype property setter + dispatch of focus, input, change, and blur events so Workday/React internal state validates.
    - **Strategy 3 (Keyboard Simulation)**: Sequenced Tab focus, Space/Arrow selection, and Enter.
  - **Hard Stop at Attempt 3**: If a field remains blocked after 3 distinct strategies, STOP IMMEDIATELY and notify Carlo for a single manual intervention.
  - **Semantic Invariance**: Never alter the substance or truthfulness of Carlo's profile answers during retries.
- **Source / Referrer Random Fallback**:
  - Attempt selection of Google or Social Media -> LinkedIn Jobs. If not registered on attempt 1, immediately pick ANY available option at random (e.g. Other, Website, Job Board) without blocking.
- **Tab Lifecycle Management**:
  - Immediately close confirmed application tabs in the background to prevent tab sprawl and browser memory bloat.

## 7. EXPERT ATS APPLICATION & DOSSIER MAXIMIZATION PROTOCOL
- **Comprehensive Document & Credentials Bundling**:
  - Always attach all relevant and permissible documents to every application: tailored Master ATS CV, cover letter, university degrees/diplomas, industry certifications (Cloud/Kubernetes/Architecture/Security), and letters of recommendation available in Carlo's dossier (`10_CV_Portfolio`).
- **Target Platform Recognition**:
  - Automatically identify the application system (Workday, Taleo, SuccessFactors, Lever, Greenhouse, PeopleSoft, custom portal) and adopt its proven field completion conventions and file parsing requirements.
- **HR Expert Strategic Matching (Truthful Lexical Framing)**:
  - Maximize ATS parsing ranking and recruiter shortlisting through deliberate semantic alignment.
  - Adapt phrasing, competence emphasis, and terminology to closely echo vacancy keywords and scoring criteria ("piegare l'application senza mentire"), while remaining 100% strictly truthful and accurate to Carlo's actual experience and qualifications.
  - Follow all site-specific instructions and modern ATS application best practices to eliminate formatting penalties or keyword omissions.

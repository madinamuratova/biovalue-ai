// The "About the tool" tab: what you can do, the idea behind it, and who it is for, in plain words.
// Market and technical statements cite the evidence library (click a reference to open it).
import { EvidenceRefs } from './ui.tsx'

const STEPS: [string, string][] = [
  ['Describe your lignin stream', 'Annual quantity, moisture, composition, equipment, and where you sell, starting from the fictional demo or the literature reference (published, cited values). Leave anything you have not measured blank: it is recorded as missing, never as zero.'],
  ['Run the four agents', 'About one to three minutes. The agents read your data and a library of verified sources; every number is calculated by tested code.'],
  ['Read the ranking and why', 'Three product pathways scored 1–5, with how much of the score could be assessed, how strong the evidence is, and indicative economics where you gave prices and costs.'],
  ['Act on the next steps', 'Three to five validation steps, an evidence explorer, a full trace of what each agent did, and an HTML or Markdown report. Rerun whenever a lab result arrives.'],
]

const PATHWAYS: { name: string; what: string; matters: string; refs: string[] }[] = [
  {
    name: 'Phenolic resins and adhesives',
    what: 'Lignin is phenolic, so it can replace part of the phenol in the phenol-formaldehyde resins used to glue plywood and other wood panels.',
    matters: 'Typical replacement is up to 50%, after an activation or depolymerization step; the IEA puts the technology at TRL 8.',
    refs: ['EV-PF-01#1', 'EV-PF-01#2', 'EV-PF-01#3'],
  },
  {
    name: 'Polyurethane materials and foams',
    what: 'Lignin’s hydroxyl groups let it replace part of the petroleum-based polyol in polyurethane foams.',
    matters: 'A total hydroxyl value above 200 mg KOH/g is cited as acceptable for rigid foam; the IEA rates these uses at TRL 6.',
    refs: ['EV-PU-01#R1', 'EV-PU-04#1'],
  },
  {
    name: 'Lignin-derived carbon materials',
    what: 'Lignin is rich in carbon, so it can become carbon fiber, hard carbon for battery anodes, or activated carbon.',
    matters: 'Purity decides which: a carbon-fiber precursor needs over 99% lignin and under 0.1% ash, while activated carbon has no strict quality limits.',
    refs: ['EV-CM-01#R1', 'EV-CM-01#R2', 'EV-CM-05#1'],
  },
]

const AUDIENCE: [string, string][] = [
  ['Pulp mill strategy and business development', 'Decide which lignin product deserves lab work, a partner conversation, or a consultant study, and explain why.'],
  ['R&D and technical managers', 'See which missing measurements (for example molecular weight, hydroxyl content, ash) would change the answer, so lab budgets go where they matter.'],
  ['Climate-tech investors and bioeconomy programs', 'Screen a mill’s lignin opportunity quickly and see how much of the case rests on evidence versus assumptions.'],
  ['Students and researchers', 'Learn how composition, technology readiness, and market evidence combine in a transparent, sourced way.'],
]

function Leaf() {
  return (
    <svg className="about-icon" viewBox="0 0 40 40" aria-hidden="true">
      <path d="M8 30 C 12 14, 26 8, 34 8 C 34 18, 26 32, 8 30 Z M8 30 L 26 14" />
    </svg>
  )
}

export function About({ onStart }: { onStart: () => void }) {
  return (
    <main className="about">
      <section className="about-hero">
        <Leaf />
        <div>
          <h2>What BioValue AI does</h2>
          <p>
            A kraft pulp mill can take lignin out of its black liquor instead of burning it. BioValue AI gives a first, honest screen of
            what that lignin could become: it ranks three product pathways for <em>your</em> stream, shows what the ranking rests on, and
            tells you what to check next. It is a starting point for a decision, not the decision itself.
          </p>
          <button className="btn primary" onClick={onStart}>Go to the assessment</button>
        </div>
      </section>

      <section className="about-card">
        <h3>What you can do with it</h3>
        <ol className="about-steps">
          {STEPS.map(([title, text], i) => (
            <li key={title}><span className="step-num">{i + 1}</span><div><strong>{title}</strong><p>{text}</p></div></li>
          ))}
        </ol>
      </section>

      <section className="about-card">
        <h3>The idea behind it, in brief</h3>
        <p className="about-lead">
          Lignin is the natural glue that holds wood fibers together. Kraft pulping dissolves it, and most of it is burned for energy.
          Whether it is worth more as a product depends on three things: does this mill’s lignin meet the product’s requirements, how mature
          is the technology, and is there documented demand? The three candidate products ask for very different things:
        </p>
        <div className="about-pathways">
          {PATHWAYS.map((p) => (
            <div key={p.name} className="about-pathway">
              <strong>{p.name}</strong>
              <p>{p.what}</p>
              <p className="ink-2">{p.matters} <EvidenceRefs refs={p.refs} /></p>
            </div>
          ))}
        </div>
        <h4>How the score works</h4>
        <ul className="about-list">
          <li><strong>Five criteria, weighted:</strong> feedstock compatibility 25%, technical readiness 20%, market evidence 20%,
            indicative economics 20%, commercialization feasibility 15%, each on a 1–5 scale.</li>
          <li><strong>Rules where possible:</strong> compatibility (your figures against the sources’ numeric specifications), readiness
            (a TRL stated in a cited source), and economics (only when you supply yield, price, and costs) are calculated by code.
            Market evidence and feasibility are agent judgments against a written rubric, with sources.</li>
          <li><strong>Gaps are not zeros:</strong> a criterion that cannot be assessed lowers <em>completeness</em>, not the score. A pathway
            with less than 60% of the weight assessed is shown as <em>insufficient data</em> with its possible range, never ranked last.</li>
          <li><strong>Volumes on a dry basis:</strong> dry mass = wet mass × (1 − moisture), because buyers and specifications work in dry tonnes.</li>
        </ul>
      </section>

      <section className="about-card">
        <h3>Who can benefit</h3>
        <div className="about-audience">
          {AUDIENCE.map(([who, why]) => <div key={who}><strong>{who}</strong><p>{why}</p></div>)}
        </div>
      </section>

      <section className="about-card about-limits">
        <h3>What it is not</h3>
        <p>
          Not an engineering approval, a business case, or proof of customer demand: it does not calculate NPV, IRR, or margins, and it
          only knows the sources in its library. The demo mill is fictional, and the literature reference combines published values from
          different studies, not one mill’s records. Use it to decide what to look at next, then confirm with lab data, buyers, and experts.
        </p>
      </section>
    </main>
  )
}

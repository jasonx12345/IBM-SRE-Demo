# IBM SRE internship demo script

Start the local app with `.venv\Scripts\python.exe -m api.demo --port 8001`, then open http://127.0.0.1:8001/. Allow about three to four minutes. The quoted text is a script you can say aloud; the bracketed lines tell you what to click.

## Opening: why I built it

> “Imagine we deliberately break part of an application during a test. The failure itself is useful only if we can answer the next question: **did our monitoring warn us about the thing we expected it to warn us about?**
>
> That is an everyday SRE concern. An SRE helps keep services reliable, and one way to build confidence is to test a failure before a real user experiences it. I wanted to build something more concrete than a dashboard full of alert counts: a way to check the *quality of the warning system* after a controlled fault test.”

## Where the IBM data came from

[Point to **Method & source** at the top of the page, or open the **IBM Research source** link at the bottom.]

> “I looked for a real, public IBM-specific dataset I could use honestly. I found **[IBM Research's ITBench-Lite dataset](https://huggingface.co/datasets/ibm-research/ITBench-Lite)** on Hugging Face. IBM Research published experiments in which faults were deliberately introduced into test systems. For each experiment, it provides a `ground_truth.yaml` file describing the expected alerts and timestamped JSON snapshots of alerts actually recorded.
>
> I downloaded the **35 SRE experiments** from a pinned version of that dataset: **1,839 alert snapshots** and their ground-truth files. I wrote the importer and comparison logic. This is real recorded data from IBM Research's test environments—not mock alerts I invented, and not private IBM customer or production data. The app runs locally from the saved report, so the demo does not need an IBM login or a live connection.”

## What the software does

[Point to the four cards.]

> “The software puts two sides of each experiment together: **what IBM expected to fire** and **what the alert snapshots show firing**. It checks the alert name and the particular service or pod, so an unrelated alert with the same name does not count as a match.
>
> Across the 35 experiments, IBM's ground truth declares **96 expected alerts**. My report finds **61 observed**, **30 not observed in the published snapshots**, and **5 unknown** because the evidence is incomplete or cannot be matched safely.
>
> These numbers are not an IBM production failure rate. They are a short list of test outcomes an SRE could inspect. An alert marked ‘not observed’ is a *question to investigate*, not proof that a real user went unwarned.”

## Show an alert that appeared

[Open **Scenario-1** in the experiment list.]

> “In this test, the load generator created a fault affecting the frontend proxy. IBM's ground truth expected an error-rate warning and a latency warning for that service. Both are marked **Observed** here.
>
> I can click **View first matching snapshot** to see the original IBM alert record, and **View original ground truth** to see where the expectation came from. That makes the result inspectable instead of asking you to trust a green badge.”

## Show why a missing warning matters

[Select **Needs review** in the Show dropdown and open **Scenario-4**.]

> “Here is the more interesting case. The ground truth expects four error-rate alerts across different services. The recorded snapshots contain matching alerts for frontend and frontend proxy, but I do not find the expected ones for product catalog or checkout.
>
> That does **not** automatically mean those two monitors were broken. It means the published capture does not show those specific warnings. An SRE would now inspect the alert rules, the test timing, and the raw evidence. The software narrows down *which expectation needs attention* rather than leaving someone to compare hundreds of JSON files by hand.”

## Show honest uncertainty

[Select **Unknown evidence** and open **Scenario-11**.]

> “This is an important guardrail: IBM published ground truth for this experiment but no alert snapshots in this subset. Calling its two expected alerts failures would be misleading. The report says **Unknown**. It refuses to turn missing evidence into a negative result.”

## Close: what I hoped to achieve

> “The point of the project is to make a fault test answer a useful SRE question: **when we intentionally create a problem, can we verify that the expected warning appeared?** I used a public IBM Research benchmark so the demo is specific to IBM, reproducible, and easy to inspect.
>
> In a real team, the next step would be to run the same kind of audit on that team's *authorized* fault-test exports, then investigate the missing matches. This prototype does not access IBM's private systems, measure whether a page reached an engineer, or claim to replace Instana or existing alert-testing tools. It shows that I can take real observability evidence, compare it carefully, and explain what the result does—and does not—prove.”

## If an interviewer asks

**“Did you get access to IBM internal data?”** “No. IBM Research publicly released ITBench-Lite. I used its recorded test alerts and ground-truth files, pinned to a specific dataset revision.”

**“What does ‘not observed’ mean?”** “No matching firing alert appeared in the published snapshots for that experiment. I would investigate the monitoring rule and capture before calling it a monitoring failure.”

**“Is this a brand-new kind of tool?”** “Related alert tests and chaos-engineering probes already exist. My contribution is a small, reproducible audit of IBM Research's published SRE experiments with direct evidence links and explicit uncertainty.”

import json, os, re
from pathlib import Path
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from promoiq.engine import analyse_episode
from promoiq.quality import evaluate_candidates

load_dotenv()
st.set_page_config(page_title="PromoIQ",page_icon="🎬",layout="wide")
st.title("🎬 PromoIQ")
st.caption("Screenplay-to-promo discovery | AI suggestions for human editorial review")
st.info("Upload timestamped screenplay files. PromoIQ suggests candidate 20–60 second moments; an editor makes the final call.")
with st.sidebar:
    st.header("Analysis settings")
    use_llm=st.checkbox("Use LLM analysis when API key is configured",value=True)
    st.caption("Without a key, the app runs its transparent heuristic baseline. Add GROQ_API_KEY to .env for LLM-assisted candidate discovery.")
    st.markdown("**Scoring weights**\n- Hook: 30%\n- Cliffhanger: 30%\n- Standalone clarity: 25%\n- Duration fit: 10%\n- Evidence completeness: 5%")
files=st.file_uploader("Upload screenplay .txt files (one episode per file)",type=["txt"],accept_multiple_files=True)
if files:
    all_results=[]
    for f in files:
        raw_text=f.getvalue().decode('utf-8',errors='replace')
        episode_match=re.search(r"^EPISODE NUMBER\s*:\s*Episode\s+(\d+)\s*$",raw_text,re.I|re.M)
        episode=f"Episode {int(episode_match.group(1))}" if episode_match else Path(f.name).stem
        result=analyse_episode(raw_text,episode,use_llm)
        all_results.append(result)
    flat=[p for r in all_results for p in r.get('promos',[])]
    flat.sort(key=lambda x:x['scores']['total_score'],reverse=True)
    quality = evaluate_candidates(flat)
    flat = quality["reviewed_candidates"]
    st.subheader("Candidate quality evaluation")
    q1,q2,q3,q4=st.columns(4)
    q1.metric("Candidates", quality["candidate_count"])
    q2.metric("Needs review", quality["needs_review_count"])
    q3.metric("Screening candidates", quality["screening_candidate_count"])
    q4.metric("Overlap pairs", quality["overlap_pairs_flagged"])
    st.caption(quality["interpretation"])
    if quality["flag_counts"]:
        st.dataframe(pd.DataFrame(
            [{"quality_flag":k,"count":v} for k,v in quality["flag_counts"].items()]
        ), width="stretch")
    st.subheader("Ranked promo candidates")
    st.caption(f"Processed {len(files)} file(s); {sum(r.get('parsed_lines',0) for r in all_results)} timed screenplay blocks; {len(flat)} candidate(s).")
    for rank,p in enumerate(flat,1):
        seg=p['segments'][0]; sc=p['scores']
        with st.expander(f"#{rank} · {p['episode']} · {seg['start_timestamp']}–{seg['end_timestamp']} · Score {sc['total_score']}/100",expanded=(rank==1)):
            a,b,c=st.columns(3); a.metric("Hook",sc['hook_score']); b.metric("Cliffhanger",sc['cliffhanger_score']); c.metric("Standalone clarity",sc['standalone_score'])
            st.markdown(f"**Hook:** {p['hook']}\n\n**Cliffhanger:** {p['cliffhanger']}\n\n**Why it may work:** {p['why_it_works']}\n\n**Context:** {p['standalone_context']}")
            evidence = p.get("scoring_evidence")
            with st.expander("Inspect actual screenplay evidence used for scoring"):
                if evidence:
                    st.markdown("**Opening evidence**")
                    st.write(evidence.get("opening_text") or "No opening evidence was recorded.")
                    st.caption(f"Selected timestamp: {evidence.get('opening_timestamp') or 'not recorded'} · Search window: {evidence.get('opening_search_window') or 'not recorded'}")
                    st.markdown("**Closing evidence**")
                    st.write(evidence.get("closing_text") or "No closing evidence was recorded.")
                    st.caption(f"Selected timestamp: {evidence.get('closing_timestamp') or 'not recorded'} · Search window: {evidence.get('closing_search_window') or 'not recorded'}")
                    st.caption(f"Selection method: {evidence.get('selection_method', 'legacy evidence selection')}")
                else:
                    st.warning("No scoring_evidence found. Confirm that the Phase 5 engine is installed and this app is using the correct project folder.")
            
            plan = p.get("multi_segment_plan")
            if plan:
                st.markdown("**Optional multi-segment edit plan**")
                for idx, part in enumerate(plan["segments"], 1):
                    st.write(f"Segment {idx} ({part.get('role', 'edit beat')}): {part['start_timestamp']}–{part['end_timestamp']}")
                st.caption(f"Combined runtime: {plan['total_duration_seconds']:.1f}s. {plan['edit_note']}")
                st.write("Continuity review flags:", ", ".join(plan.get("continuity_warnings", [])))
            if p.get("quality_flags"):
                st.warning("Quality review flags: " + ", ".join(p["quality_flags"]))
            else:
                st.success("No automated quality flags; human review is still required.")
            st.caption(f"Quality tier: {p.get('quality_tier', 'unclassified')} · Method: {p['method']} · Editor verification required")
    st.subheader("Processing report")
    st.dataframe(pd.DataFrame([{"episode":r['episode'],"status":r['status'],"timestamped_lines":r.get('parsed_lines',0),"candidates":len(r.get('promos',[]))} for r in all_results]),width="stretch")
    out={"project":"PromoIQ","results":all_results,"ranked_promos":flat}
    blob=json.dumps(out,indent=2,ensure_ascii=False).encode()
    st.download_button("Download raw JSON outputs",blob,"promoiq_raw_outputs.json","application/json")
    rows=[]
    for p in flat:
        s=p['segments'][0]; rows.append({"episode":p['episode'],"start":s['start_timestamp'],"end":s['end_timestamp'],"score":p['scores']['total_score'],"hook":p['hook'],"cliffhanger":p['cliffhanger'],"why_it_works":p['why_it_works'],"method":p['method']})
    st.download_button("Download ranked CSV",pd.DataFrame(rows).to_csv(index=False).encode(),"promoiq_ranked_promos.csv","text/csv")
    st.download_button("Download processing report",json.dumps([{k:v for k,v in r.items() if k!='promos'} for r in all_results],indent=2).encode(),"promoiq_processing_report.json","application/json")
    quality_report = {k:v for k,v in quality.items() if k != "reviewed_candidates"}
    st.download_button("Download quality evaluation JSON", json.dumps(quality_report,indent=2).encode(), "promoiq_quality_report.json", "application/json")
    quality_rows = []
    for p in flat:
        seg = p.get("segments", [{}])[0]
        quality_rows.append({
            "episode":p.get("episode"), "start":seg.get("start_timestamp"),
            "end":seg.get("end_timestamp"), "score":p.get("scores",{}).get("total_score"),
            "quality_tier":p.get("quality_tier"),
            "quality_flags":"; ".join(p.get("quality_flags",[])),
            "hook":p.get("hook"), "cliffhanger":p.get("cliffhanger"),
            "why_it_works":p.get("why_it_works")
        })
    st.download_button("Download quality review CSV", pd.DataFrame(quality_rows).to_csv(index=False).encode(), "promoiq_quality_review.csv", "text/csv")
else:
    st.markdown("### Quick start")
    st.code("pip install -r requirements.txt\nstreamlit run app.py",language="bash")
    st.markdown("Upload one or more timestamped `.txt` screenplays to get started.")

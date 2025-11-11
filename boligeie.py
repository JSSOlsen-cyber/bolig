import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json

# Norwegian financial constants
SKATTESATS_RENTEFRADRAG = 0.22  # 22% tax deduction on mortgage interest
DOKUMENTAVGIFT_PROSENT = 0.025  # 2.5% document fee
TINGLYSNING_SKJOETE = 585  # Deed registration fee
TINGLYSNING_PANT = 585  # Mortgage registration fee

COLORS = {
    # Hovedfarger for personer - mer vibrant for dark mode
    'person_b': '#818CF8',  # Lighter Indigo
    'person_a': '#F472B6',  # Lighter Rosa
    
    # Status farger - justert for dark mode
    'success': '#34D399',   # Lighter Emerald
    'warning': '#FBBF24',   # Lighter Amber
    'danger': '#F87171',    # Lighter Red
    'info': '#60A5FA',      # Lighter Blue
    
    # Nøytrale for dark theme
    'primary': '#A78BFA',   # Lighter Purple
    'secondary': '#94A3B8', # Light Slate
    'light': '#475569',     # Medium slate (for grid lines)
    'dark': '#F1F5F9',      # Light text on dark bg
    'bg_dark': '#0F172A',   # Dark background
    'bg_card': '#1E293B',   # Card background
    
    # Text colors
    'text_primary': '#F1F5F9',
    'text_secondary': '#CBD5E1',
    'text_muted': '#94A3B8',

    # Bar colors positive/negative
    'bar_positive': '#34D399',  # Green
    'bar_negative': '#F87171',   # Red

}

# Sett opp siden
st.set_page_config(
    page_title="Boliglånskalkulator",
    page_icon="🏠",
    layout="wide"
)

# Initialiser session state
if 'scenarios' not in st.session_state:
    st.session_state.scenarios = []
if 'current_scenario' not in st.session_state:
    st.session_state.current_scenario = None

# Hjelpefunksjoner
@st.cache_data
def beregn_terminbelop(laan, rente, nedbetalingstid_aar):
    """Beregn månedlig terminbeløp for annuitetslån"""
    if rente == 0:
        return laan / (nedbetalingstid_aar * 12)
    
    maanedlig_rente = rente / 100 / 12
    antall_terminer = nedbetalingstid_aar * 12
    
    terminbelop = laan * (maanedlig_rente * (1 + maanedlig_rente)**antall_terminer) / \
                  ((1 + maanedlig_rente)**antall_terminer - 1)
    
    return terminbelop

@st.cache_data
def beregn_amortiseringsplan(laan, rente, nedbetalingstid_aar, antall_aar=None):
    """
    Generer full amortiseringsplan med korrekt rente/avdrag-fordeling

    Returnerer DataFrame med månedlige detaljer
    """
    if antall_aar is None:
        antall_aar = min(10, nedbetalingstid_aar)  # Standard vis 10 år
    
    maanedlig_rente = rente / 100 / 12
    terminbelop = beregn_terminbelop(laan, rente, nedbetalingstid_aar)
    
    gjenstaaende = laan
    plan = []
    
    for mnd in range(antall_aar * 12):
        if gjenstaaende <= 0:
            break
            
        # Renter denne måneden
        renter = gjenstaaende * maanedlig_rente
        
        # Avdrag denne måneden
        avdrag = terminbelop - renter
        
        # Oppdater gjenstående
        gjenstaaende -= avdrag
        
        plan.append({
            'År': (mnd // 12) + 1,
            'Måned': (mnd % 12) + 1,
            'Terminbeløp': terminbelop,
            'Renter': renter,
            'Avdrag': avdrag,
            'Gjenstående': max(0, gjenstaaende),
            'Skattefradrag': renter * SKATTESATS_RENTEFRADRAG,
            'Netto kostnad': terminbelop - (renter * SKATTESATS_RENTEFRADRAG)
        })
    
    return pd.DataFrame(plan)


def beregn_skattefradrag(rentekostnad):
    """Beregn skattefradrag på rentekostnader (22% i Norge)"""
    return rentekostnad * SKATTESATS_RENTEFRADRAG

def beregn_belastningsgrad(boligutgifter, nettoinntekt):
    """
    Beregn belastningsgrad som prosent av nettoinntekt.

    Dette er den vanlige beregningen som banker bruker:
    Boligutgifter (før skattefradrag) / Nettoinntekt (før skattefradrag)

    Dette reflekterer faktisk kontantstrøm, siden du betaler full kostnad
    hver måned og kun får skattefordelen gjennom høyere nettoinntekt senere.
    """
    if nettoinntekt == 0:
        return 0
    return (boligutgifter / nettoinntekt) * 100

def beregn_effektiv_belastning(boligutgifter, nettoinntekt, skattefradrag_mnd):
    """
    Beregn effektiv belastningsgrad etter skattefordel.

    Dette viser den langsiktige økonomiske belastningen når skattefradraget
    er tatt i betraktning (enten gjennom justering av skattekort eller
    ved skatteoppgjør).

    Beregning: Boligutgifter (før fradrag) / (Nettoinntekt + skattefradrag)
    """
    if nettoinntekt == 0:
        return 0
    return (boligutgifter / (nettoinntekt + skattefradrag_mnd)) * 100

@st.cache_data
def generer_renteprognose(basis_rente, prognose_type="norges_bank"):
    """
    Generer renteprognose basert på Norges Banks styringsrenteprognose juni 2025
    Boliglånsrenten er typisk 1.5-2% over styringsrenten
    """
    
    # Norges Banks styringsrenteprognose juni 2025
    styringsrente_prognose = {
        2025: 4.25,
        2026: 4.0,
        2027: 3.5,
        2028: 3.1,
        2029: 3.0,
        2030: 3.0,  # Antar stabilisering
        2031: 3.0,
        2032: 3.0,
        2033: 3.0,
        2034: 3.0
    }
    
    aar = list(range(2025, 2035))
    
    if prognose_type == "norges_bank":
        # Hovedprognose: Norges Banks prognose + standard påslag
        passlag = 1.5  # Standard påslag fra styringsrente til boliglånsrente
        renter = [styringsrente_prognose[year] + passlag for year in aar]
        
    elif prognose_type == "optimistisk":
        # Optimistisk: Norges Banks prognose + lavt påslag (konkurranse i markedet)
        passlag = 1.0  # Lavere påslag pga konkurranse
        renter = [styringsrente_prognose[year] + passlag for year in aar]
        
    elif prognose_type == "pessimistisk":
        # Pessimistisk: Høyere styringsrente enn prognose + høyt påslag
        passlag = 2.0  # Høyere påslag
        # Legger til 0.5% ekstra på styringsrenten
        renter = [min(8.0, styringsrente_prognose[year] + 0.5 + passlag) for year in aar]
        
    else:  # fallback til gammel modell
        # Gammel modell for bakoverkompatibilitet
        if prognose_type == "lav":
            renter = [max(1.5, basis_rente - 0.1 * i) for i in range(10)]
        elif prognose_type == "moderat":
            renter = []
            current = basis_rente
            for i in range(10):
                if i < 3:
                    current += 0.2
                elif i < 5:
                    current += 0.1
                else:
                    current += 0.05
                renter.append(min(6.0, current))
        else:  # høy
            renter = []
            current = basis_rente
            for i in range(10):
                if i < 2:
                    current += 0.5
                elif i < 5:
                    current += 0.3
                else:
                    current += 0.1
                renter.append(min(8.0, current))
    
    return pd.DataFrame({'År': aar, 'Rente': renter})

def beregn_fordeling(total_kostnad, inntekt_a, inntekt_b, fordeling_type, custom_split=None):
    """Beregn fordeling av kostnader mellom to personer"""
    if fordeling_type == "50/50":
        return total_kostnad / 2, total_kostnad / 2
    
    elif fordeling_type == "Proporsjonal etter inntekt":
        if inntekt_a + inntekt_b == 0:
            return 0, 0
        andel_a = inntekt_a / (inntekt_a + inntekt_b)
        return total_kostnad * andel_a, total_kostnad * (1 - andel_a)
    
    elif fordeling_type == "Egendefinert":
        andel_a = custom_split / 100
        return total_kostnad * andel_a, total_kostnad * (1 - andel_a)
    
    return total_kostnad / 2, total_kostnad / 2

def lagre_scenario_til_fil(scenario_data):
    """Konverterer scenario til JSON-streng for nedlasting"""
    # Legg til timestamp
    scenario_data['lagret_tid'] = datetime.now().isoformat()
    
    # Konverter til JSON
    json_str = json.dumps(scenario_data, indent=2, ensure_ascii=False)
    return json_str

def last_scenario_fra_fil(uploaded_file):
    """Laster scenario fra opplastet JSON-fil"""
    try:
        # Les filen
        json_str = uploaded_file.read().decode('utf-8')
        scenario_data = json.loads(json_str)
        return scenario_data
    except Exception as e:
        st.error(f"Kunne ikke laste scenario: {str(e)}")
        return None

# Hovedapplikasjon
st.title("🏠 Boliglånskalkulator med justerbar fordeling")


# Hovedinnhold i tabs
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "🏡 Boligdata", 
    "💰 Inntekter & Fordeling", 
    "📈 Renteprognoser",
    "⚠️ Stress-testing", 
    "📊 Sammendrag",
    "💪 Budsjettering og bærekraftighet",
    "🏠 Salg av bolig",
    "💰 Ekstra nedbetaling"
])

with tab1:
    st.header("Boliginformasjon")
    
    col1, col2 = st.columns(2)
    
    with col1:
        boligpris = st.number_input(
            "Boligpris (kr)",
            min_value=500000,
            max_value=15000000,
            value=4500000,
            step=100000,
            help="Total kjøpesum for boligen",
            key="boligpris"
        )
        
        egenkapital = st.number_input(
            "Egenkapital (kr)",
            min_value=0,
            max_value=boligpris,
            value=1300000,
            step=50000,
            help="Minimum 15% anbefales",
            key="egenkapital"
        )
        
        egenkapital_prosent = (egenkapital / boligpris) * 100
        
        if egenkapital_prosent < 10:
            st.error(f"⚠️ Egenkapital er kun {egenkapital_prosent:.1f}%. Minimum 10% kreves!")
        elif egenkapital_prosent < 15:
            st.warning(f"⚠️ Egenkapital er {egenkapital_prosent:.1f}%. 15% anbefales for bedre betingelser.")
        else:
            st.success(f"✅ Egenkapital: {egenkapital_prosent:.1f}%")

            # NYE FELTER FOR EGENKAPITAL-FORDELING
            st.markdown("**Fordeling av egenkapital**")
            
            egenkapital_fordeling_type = st.radio(
                "Hvordan fordeles egenkapitalen?",
                ["Lik fordeling (50/50)", "Ulik fordeling"],
                horizontal=True
            )
            
            if egenkapital_fordeling_type == "Ulik fordeling":
                egenkapital_a = st.number_input(
                    f"Egenkapital fra Thale (kr)",
                    min_value=0,
                    max_value=egenkapital,
                    value=int(egenkapital * 0.4),
                    step=10000,
                    key="egenkapital_a"
                )
                egenkapital_b = egenkapital - egenkapital_a
                st.info(f"Egenkapital fra Jonas: {egenkapital_b:,.0f} kr")
            else:
                egenkapital_a = egenkapital / 2
                egenkapital_b = egenkapital / 2
            
            # Vis eierandel basert på egenkapital
            eierandel_a = (egenkapital_a / boligpris) * 100
            eierandel_b = (egenkapital_b / boligpris) * 100
            
            st.markdown("**Initiell eierandel (kun fra EK)**")
            st.caption(f"Thale: {eierandel_a:.1f}% | Jonas: {eierandel_b:.1f}%")

    with col2:
        rente = st.number_input(
            "Rente (%)",
            min_value=0.0,
            max_value=10.0,
            value=4.99,
            step=0.1,
            help="Nominell rente på boliglånet",
            key="rente"
        )

        nedbetalingstid = st.number_input(
            "Nedbetalingstid (år)",
            min_value=5,
            max_value=30,
            value=25,
            step=1,
            key="nedbetalingstid"
        )

        felleskostnader = st.number_input(
            "Felleskostnader (kr/mnd)",
            min_value=0,
            max_value=10000,
            value=3500,
            step=500,
            help="Månedlige felleskostnader/kommunale avgifter",
            key="felleskostnader"
        )
    
    # Beregn lånebeløp og omkostninger
    laanebelop = boligpris - egenkapital
    dokumentavgift = boligpris * DOKUMENTAVGIFT_PROSENT
    tinglysning = TINGLYSNING_SKJOETE + TINGLYSNING_PANT
    totale_omkostninger = dokumentavgift + tinglysning
    
    st.markdown("### 📋 Omkostninger ved kjøp")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Dokumentavgift (2.5%)", f"{dokumentavgift:,.0f} kr")
    with col2:
        st.metric("Tinglysning", f"{tinglysning:,.0f} kr")
    with col3:
        st.metric("Totale omkostninger", f"{totale_omkostninger:,.0f} kr")


with tab2:
    st.header("Inntekter og kostnadsfordeling")
    
    # Inntektsinformasjon
    st.subheader("💼 Inntektsinformasjon")
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Person A**")
        navn_a = st.text_input("Navn", value="Thale", key="navn_a")
        brutto_aar_a = st.number_input(
            "Netto månedslønn (kr)", 
            min_value=0, 
            max_value=3000000, 
            value=37900, 
            step=1000,
            key="brutto_a"
        )
        # Forenklet skatteberegning (ca 30% gjennomsnitt)
        netto_mnd_a = brutto_aar_a
        
        jobtype_a = st.selectbox(
            "Jobbtype", 
            ["Fast ansatt", "Midlertidig", "Selvstendig", "Frilanser"],
            key="jobtype_a"
        )
    
    with col2:
        st.markdown("**Person B**")
        navn_b = st.text_input("Navn", value="Jonas", key="navn_b")
        brutto_aar_b = st.number_input(
            "Netto månedsinntekt (kr)", 
            min_value=0, 
            max_value=3000000, 
            value=58500, 
            step=1000,
            key="brutto_b"
        )
        netto_mnd_b = brutto_aar_b
        
        jobtype_b = st.selectbox(
            "Jobbtype", 
            ["Fast ansatt", "Midlertidig", "Selvstendig", "Frilanser"],
            key="jobtype_b"
        )
    
    # Fordelingsmodell
    st.subheader("⚖️ Fordelingsmodell")
    
    fordeling_type = st.radio(
        "Velg hvordan kostnadene skal fordeles",
        ["50/50", "Proporsjonal etter inntekt", "Egendefinert"],
        horizontal=True
    )
    
    custom_split = None
    if fordeling_type == "Egendefinert":
        custom_split = st.slider(
            f"Andel for {navn_a} (%)",
            min_value=0,
            max_value=100,
            value=50,
            step=5,
            key="custom_split"
        )
        st.info(f"{navn_a}: {custom_split}% | {navn_b}: {100-custom_split}%")
    
    # Beregninger
    terminbelop = beregn_terminbelop(laanebelop, rente, nedbetalingstid)

    # Beregn rentekostnad for første år (forenklet)
    rentekostnad_mnd = (laanebelop * (rente / 100)) / 12
    avdrag_mnd = terminbelop - rentekostnad_mnd
    skattefradrag_mnd = beregn_skattefradrag(rentekostnad_mnd)

    # Total månedlig kostnad (faktisk utbetaling)
    total_mnd_kostnad = terminbelop + felleskostnader

    # Fordel kostnadene (før skattefradrag - dette er faktisk utbetaling)
    kostnad_a, kostnad_b = beregn_fordeling(
        total_mnd_kostnad,
        brutto_aar_a,
        brutto_aar_b,
        fordeling_type,
        custom_split
    )

    # Fordel skattefradrag
    skattefradrag_a, skattefradrag_b = beregn_fordeling(
        skattefradrag_mnd,
        brutto_aar_a,
        brutto_aar_b,
        fordeling_type,
        custom_split
    )
    
    # Vis fordelingsresultat
    st.subheader("📊 Resultat av fordeling")

    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        # Visualiser fordeling
        fig_fordeling = go.Figure(data=[
            go.Bar(name=navn_a, x=['Kostnad', 'Inntekt'], 
                   y=[kostnad_a, netto_mnd_a], 
                   text=[f'{kostnad_a:,.0f}', f'{netto_mnd_a:,.0f}'],
                   textposition='auto'),
            go.Bar(name=navn_b, x=['Kostnad', 'Inntekt'], 
                   y=[kostnad_b, netto_mnd_b],
                   text=[f'{kostnad_b:,.0f}', f'{netto_mnd_b:,.0f}'],
                   textposition='auto')
        ])
        fig_fordeling.update_layout(
            title="Månedlig kostnad vs inntekt",
            yaxis_title="Kroner",
            barmode='group',
            height=400
        )
        st.plotly_chart(fig_fordeling, use_container_width=True)
    
    # Detaljert oversikt per person
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"### 👤 {navn_a}")

        # Beregn begge typer belastningsgrad
        belastning_a = beregn_belastningsgrad(kostnad_a, netto_mnd_a)
        effektiv_belastning_a = beregn_effektiv_belastning(kostnad_a, netto_mnd_a, skattefradrag_a)
        disponibel_før_skatt_a = netto_mnd_a - kostnad_a
        disponibel_etter_skatt_a = netto_mnd_a + skattefradrag_a - kostnad_a

        metrics_col1, metrics_col2 = st.columns(2)
        with metrics_col1:
            st.metric("Månedlig kostnad", f"{kostnad_a:,.0f} kr",
                     help="Dette er det du faktisk betaler hver måned")
            st.metric("Skattefradrag", f"{skattefradrag_a:,.0f} kr",
                     help="22% av dine rentekostnader - kommer som høyere nettoinntekt")
            st.metric("Belastningsgrad", f"{belastning_a:.1f}%",
                     delta="God" if belastning_a < 30 else "Høy" if belastning_a < 35 else "Kritisk",
                     help="Kostnad som % av nettoinntekt - dette ser banken på")
        with metrics_col2:
            st.metric("Disponibelt før skattefradrag", f"{disponibel_før_skatt_a:,.0f} kr",
                     help="Det du har igjen etter å ha betalt boligkostnadene")
            st.metric("Disponibelt etter skattefradrag", f"{disponibel_etter_skatt_a:,.0f} kr",
                     help="Det du har igjen når skattefradraget er regnet inn")
            st.metric("Effektiv belastning", f"{effektiv_belastning_a:.1f}%",
                     delta="God" if effektiv_belastning_a < 25 else "Høy" if effektiv_belastning_a < 30 else "Kritisk",
                     help="Langsiktig belastning når skattefradrag er inkludert")

        if belastning_a > 35:
            st.error(f"⚠️ Belastningsgrad over 35% - kan være risikabelt!")
        elif belastning_a > 30:
            st.warning(f"⚠️ Belastningsgrad over 30% - vær forsiktig")
        else:
            st.success(f"✅ Belastningsgrad under 30% - bærekraftig")

    with col2:
        st.markdown(f"### 👤 {navn_b}")

        # Beregn begge typer belastningsgrad
        belastning_b = beregn_belastningsgrad(kostnad_b, netto_mnd_b)
        effektiv_belastning_b = beregn_effektiv_belastning(kostnad_b, netto_mnd_b, skattefradrag_b)
        disponibel_før_skatt_b = netto_mnd_b - kostnad_b
        disponibel_etter_skatt_b = netto_mnd_b + skattefradrag_b - kostnad_b

        metrics_col1, metrics_col2 = st.columns(2)
        with metrics_col1:
            st.metric("Månedlig kostnad", f"{kostnad_b:,.0f} kr",
                     help="Dette er det du faktisk betaler hver måned")
            st.metric("Skattefradrag", f"{skattefradrag_b:,.0f} kr",
                     help="22% av dine rentekostnader - kommer som høyere nettoinntekt")
            st.metric("Belastningsgrad", f"{belastning_b:.1f}%",
                     delta="God" if belastning_b < 30 else "Høy" if belastning_b < 35 else "Kritisk",
                     help="Kostnad som % av nettoinntekt - dette ser banken på")
        with metrics_col2:
            st.metric("Disponibelt før skattefradrag", f"{disponibel_før_skatt_b:,.0f} kr",
                     help="Det du har igjen etter å ha betalt boligkostnadene")
            st.metric("Disponibelt etter skattefradrag", f"{disponibel_etter_skatt_b:,.0f} kr",
                     help="Det du har igjen når skattefradraget er regnet inn")
            st.metric("Effektiv belastning", f"{effektiv_belastning_b:.1f}%",
                     delta="God" if effektiv_belastning_b < 25 else "Høy" if effektiv_belastning_b < 30 else "Kritisk",
                     help="Langsiktig belastning når skattefradrag er inkludert")

        if belastning_b > 35:
            st.error(f"⚠️ Belastningsgrad over 35% - kan være risikabelt!")
        elif belastning_b > 30:
            st.warning(f"⚠️ Belastningsgrad over 30% - vær forsiktig")
        else:
            st.success(f"✅ Belastningsgrad under 30% - bærekraftig")


       # Viktig informasjon om skattefradrag
    st.info("""
        **💡 Viktig om skattefradrag:**

        Skattefradraget (22% av rentekostnader) fungerer IKKE som en reduksjon i månedsbeløpet du betaler til banken.
        I stedet får du skattefordelen som **høyere nettoinntekt** gjennom:
        - Justering av skattekortet (lavere trekk hver måned), eller
        - Ved skatteoppgjøret (penger tilbake årlig)

        Derfor viser vi:
        - **Belastningsgrad**: Det banken ser på - faktisk kostnad vs nåværende nettoinntekt
        - **Effektiv belastning**: Langsiktig belastning når du har justert skattekortet
        """)
with tab3:
    st.header("Renteprognoser")
    
    st.markdown("""
    Se hvordan ulike rentescenarier påvirker deres økonomi over de neste 10 årene.
    Basert på Norges Banks styringsrenteprognose fra juni 2025.
    """)
    
    # Info-boks om Norges Banks prognose
    st.info("""
    📊 **Norges Banks prognose (juni 2025)**
    - Styringsrenten forventes å holde seg på 4% ut 2025
    - Gradvis nedgang til 3.0% mot 2029
    - Boliglånsrenten ligger typisk 1.0-2.0% over styringsrenten
    """)
    
    # Generer prognoser med nye typer
    prognose_norges_bank = generer_renteprognose(rente, "norges_bank")
    prognose_optimistisk = generer_renteprognose(rente, "optimistisk")
    prognose_pessimistisk = generer_renteprognose(rente, "pessimistisk")
    
    styringsrente_data = {
        2025: 4, 2026: 3.81, 2027: 3.29, 2028: 3.1, 2029: 3.0,
        2030: 3.0, 2031: 3.0, 2032: 3.0, 2033: 3.0, 2034: 3.0
    }
    fig_rente = go.Figure()

    # Styringsrente for dark theme
    fig_rente.add_trace(go.Scatter(
        x=list(styringsrente_data.keys()),
        y=list(styringsrente_data.values()),
        mode='lines',
        name='Styringsrente (Norges Bank)',
        line=dict(color=COLORS['text_muted'], dash='dash', width=2),
        opacity=0.6,
        hovertemplate='Styringsrente: %{y:.1f}%<extra></extra>'
    ))

    # Renteprognoser med lyse farger for dark mode
    fig_rente.add_trace(go.Scatter(
        x=prognose_optimistisk['År'], 
        y=prognose_optimistisk['Rente'],
        mode='lines+markers',
        name='Optimistisk (+1.0%)',
        line=dict(color=COLORS['success'], width=2.5),
        marker=dict(
            size=7, 
            color=COLORS['success'],
            line=dict(width=1, color='rgba(52, 211, 153, 0.3)')
        ),
        hovertemplate='Optimistisk: %{y:.1f}%<extra></extra>'
    ))

    fig_rente.add_trace(go.Scatter(
        x=prognose_norges_bank['År'], 
        y=prognose_norges_bank['Rente'],
        mode='lines+markers',
        name='Hovedscenario (+1.5%)',
        line=dict(color=COLORS['info'], width=3.5),
        marker=dict(
            size=9,
            color=COLORS['info'],
            line=dict(width=1, color='rgba(96, 165, 250, 0.3)')
        ),
        hovertemplate='Hovedscenario: %{y:.1f}%<extra></extra>'
    ))

    fig_rente.add_trace(go.Scatter(
        x=prognose_pessimistisk['År'], 
        y=prognose_pessimistisk['Rente'],
        mode='lines+markers',
        name='Pessimistisk (+2.0%)',
        line=dict(color=COLORS['danger'], width=2.5),
        marker=dict(
            size=7,
            color=COLORS['danger'],
            line=dict(width=1, color='rgba(248, 113, 113, 0.3)')
        ),
        hovertemplate='Pessimistisk: %{y:.1f}%<extra></extra>'
    ))

    # Dagens rente for dark theme
    fig_rente.add_shape(
        type="line",
        x0=2025, x1=2034,
        y0=rente, y1=rente,
        line=dict(
            color=COLORS['warning'],
            width=2,
            dash="dot"
        )
    )

    fig_rente.add_annotation(
        x=2034,
        y=rente,
        text=f"Din rente: {rente}%",
        showarrow=True,
        arrowhead=2,
        arrowsize=1,
        arrowwidth=2,
        arrowcolor=COLORS['warning'],
        font=dict(size=11, color=COLORS['warning'], weight='bold'),
        bgcolor=COLORS['bg_card'],
        bordercolor=COLORS['warning'],
        borderwidth=1
    )

    fig_rente.update_layout(
        title=dict(
            text="📈 Renteprognose 2025-2034 (Norges Bank)",
            font=dict(size=20, color=COLORS['text_primary'])
        ),
        xaxis=dict(
            title=dict(text="År", font=dict(color=COLORS['text_secondary'])),
            gridcolor=COLORS['light'],
            showgrid=True,
            tickfont=dict(color=COLORS['text_secondary']),

        ),
        yaxis=dict(
            title=dict(text="Rente (%)", font=dict(color=COLORS['text_secondary'])),
            range=[2.5, 8],
            gridcolor=COLORS['light'],
            showgrid=True,
            ticksuffix="%",
            tickfont=dict(color=COLORS['text_secondary']),

        ),
        height=500,
        hovermode='x unified',
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor='rgba(30, 41, 59, 0.9)',
            bordercolor=COLORS['light'],
            borderwidth=1,
            font=dict(size=11, color=COLORS['text_primary'])
        ),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        hoverlabel=dict(
            bgcolor=COLORS['bg_card'],
            font_color=COLORS['text_primary']
        )
    )

    st.plotly_chart(fig_rente, use_container_width=True)
    
    st.subheader("💰 Kostnadseffekt av rentescenarier")
    # Bruk Norges Banks prognose for spesifikke år
    rente_scenarios = [
        ("Dagens rente", rente),
        ("2026 (NB prognose)", 3.81 + 1.0),  # Styringsrente + påslag
        ("2027 (NB prognose)", 3.29 + 1.0),
        ("2028 (NB prognose)", 3.1 + 1.0),
        ("2029+ (NB prognose)", 3.0 + 1.0),
        ("+1% fra dagens", rente + 1),
        ("+2% fra dagens", rente + 2),
        ("Krisescenario", 8.0)
    ]
    
    scenario_data = []
    for scenario_navn, scenario_rente in rente_scenarios:
        scenario_terminbelop = beregn_terminbelop(laanebelop, scenario_rente, nedbetalingstid)
        scenario_rentekostnad = (laanebelop * (scenario_rente / 100)) / 12
        scenario_skattefradrag = beregn_skattefradrag(scenario_rentekostnad)
        scenario_total = scenario_terminbelop + felleskostnader  # Faktisk utbetaling

        scenario_kostnad_a, scenario_kostnad_b = beregn_fordeling(
            scenario_total, brutto_aar_a, brutto_aar_b, fordeling_type, custom_split
        )

        scenario_skattefradrag_a, scenario_skattefradrag_b = beregn_fordeling(
            scenario_skattefradrag, brutto_aar_a, brutto_aar_b, fordeling_type, custom_split
        )

        # Beregn endring fra dagens situasjon
        endring_total = scenario_total - total_mnd_kostnad
        endring_prosent = (endring_total / total_mnd_kostnad) * 100 if total_mnd_kostnad > 0 else 0

        scenario_data.append({
            'Scenario': scenario_navn,
            'Rente': f"{scenario_rente:.1f}%",
            'Total/mnd': scenario_total,
            'Endring': endring_total,
            'Endring %': endring_prosent,
            f'{navn_a}': scenario_kostnad_a,
            f'{navn_b}': scenario_kostnad_b,
            f'Belastning {navn_a}': beregn_belastningsgrad(scenario_kostnad_a, netto_mnd_a),
            f'Belastning {navn_b}': beregn_belastningsgrad(scenario_kostnad_b, netto_mnd_b),
            f'Eff. belastning {navn_a}': beregn_effektiv_belastning(scenario_kostnad_a, netto_mnd_a, scenario_skattefradrag_a),
            f'Eff. belastning {navn_b}': beregn_effektiv_belastning(scenario_kostnad_b, netto_mnd_b, scenario_skattefradrag_b)
        })
    
    df_scenarios = pd.DataFrame(scenario_data)
    
    # Vis tabell med forbedret formatering
    st.dataframe(
        df_scenarios.style.format({
            'Total/mnd': '{:,.0f} kr',
            'Endring': lambda x: f"{x:+,.0f} kr" if x != 0 else "-",
            'Endring %': lambda x: f"{x:+.1f}%" if x != 0 else "-",
            f'{navn_a}': '{:,.0f} kr',
            f'{navn_b}': '{:,.0f} kr',
            f'Belastning {navn_a}': '{:.1f}%',
            f'Belastning {navn_b}': '{:.1f}%',
            f'Eff. belastning {navn_a}': '{:.1f}%',
            f'Eff. belastning {navn_b}': '{:.1f}%'
        }).background_gradient(subset=[f'Belastning {navn_a}', f'Belastning {navn_b}'],
                               cmap='RdYlGn_r', vmin=20, vmax=40)
        .bar(subset=['Endring'], color=['#d65f5f', '#5fba7d'], align='zero'),
        use_container_width=True
    )
    
    # Legg til forklarende tekst
    st.caption("""
    **Forklaring:**
    - Prognosene er basert på Norges Banks styringsrenteprognose fra juni 2025
    - Boliglånsrenten antas å ligge 1.5% over styringsrenten (standard påslag)
    - Belastningsgrad under 30% regnes som bærekraftig
    - Skattefradrag (22% av rentekostnader) er inkludert i beregningene
    """)

with tab4:
    st.header("Stress-testing")
    
    st.markdown("""
    Test hvordan økonomien takler ulike krisescenarier. 
    Dette hjelper dere å forstå risikoen og planlegge for det uventede.
    """)
    
    # Stress-test scenarios
    stress_scenarios = {
        f"✅ Normal situasjon": {
            'inntekt_a': netto_mnd_a,
            'inntekt_b': netto_mnd_b,
            'rente': rente,
            'beskrivelse': "Begge i full jobb, normal rente"
        },
        f"⚠️ {navn_a} mister jobben": {
            'inntekt_a': min(netto_mnd_a * 0.6, 22000),
            'inntekt_b':  netto_mnd_b ,
            'rente': rente,
            'beskrivelse': f"Kun {navn_b} har inntekt"
        },
        f"⚠️ {navn_b} mister jobben": {
            'inntekt_a': netto_mnd_a,
            'inntekt_b': min(netto_mnd_b * 0.6, 22000),
            'rente': rente,
            'beskrivelse': f"Kun {navn_a} har inntekt"
        },

        f"⚠️ Begge mister jobben": {
            'inntekt_a': min(netto_mnd_a * 0.6, 22000),
            'inntekt_b': min(netto_mnd_b * 0.6, 22000),
            'rente': rente,
            'beskrivelse': "Begge uten jobb, dagpenger"
        },
    
        f"🤒 {navn_a} langtidssykemeldt": {
            'inntekt_a': min(netto_mnd_a * 0.66, 22000),
            'inntekt_b': netto_mnd_b,
            'rente': rente,
            'beskrivelse': f"{navn_a} på 66% sykepenger"
        },
        f"📈 Rentekrise (+3%)": {
            'inntekt_a': netto_mnd_a,
            'inntekt_b': netto_mnd_b,
            'rente': rente + 3,
            'beskrivelse': "Kraftig renteøkning"
        },
        f"🔥 Perfekt storm": {
            'inntekt_a': min(netto_mnd_a * 0.6, 22000),
            'inntekt_b': min(netto_mnd_b * 0.6, 22000),
            'rente': rente + 2,
            'beskrivelse': "Reduserte inntekter + høyere rente"
        }
    }
    
    stress_results = []
    
    for scenario_navn, params in stress_scenarios.items():
        # Beregn for stress scenario
        stress_terminbelop = beregn_terminbelop(laanebelop, params['rente'], nedbetalingstid)
        stress_rentekostnad = (laanebelop * (params['rente'] / 100)) / 12
        stress_skattefradrag = beregn_skattefradrag(stress_rentekostnad)
        stress_total = stress_terminbelop + felleskostnader  # Faktisk utbetaling

        # Netto inntekter i stress scenario
        stress_netto_a = (params['inntekt_a'] )
        stress_netto_b = (params['inntekt_b'] )
        total_netto = stress_netto_a + stress_netto_b

        # Total netto inkludert skattefradrag (langsiktig)
        total_netto_med_fradrag = total_netto + stress_skattefradrag

        # Kan de håndtere kostnadene?
        kan_betale = total_netto >= stress_total
        margin = total_netto - stress_total
        margin_med_fradrag = total_netto_med_fradrag - stress_total

        stress_results.append({
            'Scenario': scenario_navn,
            'Beskrivelse': params['beskrivelse'],
            'Total inntekt': total_netto,
            'Total kostnad': stress_total,
            'Skattefradrag': stress_skattefradrag,
            'Margin før fradrag': margin,
            'Margin med fradrag': margin_med_fradrag,
            'Status': '✅ OK' if kan_betale else '❌ KRITISK'
        })
    
    df_stress = pd.DataFrame(stress_results)
    
    # Vis resultater
    st.dataframe(
        df_stress.style.format({
            'Total inntekt': '{:,.0f} kr',
            'Total kostnad': '{:,.0f} kr',
            'Skattefradrag': '{:,.0f} kr',
            'Margin før fradrag': '{:,.0f} kr',
            'Margin med fradrag': '{:,.0f} kr'
        }).apply(lambda x: ['background-color: #ffcccc' if v < 0 else ''
                           for v in x], subset=['Margin før fradrag']),
        use_container_width=True,
        hide_index=True
    )
    
    # Visualiser stress-test
    fig_stress = go.Figure()
    
    fig_stress.add_trace(go.Bar(
        name='Inntekt',
        x=[r['Scenario'] for r in stress_results],
        y=[r['Total inntekt'] for r in stress_results],
        marker_color=COLORS['success']
    ))
    
    fig_stress.add_trace(go.Bar(
        name='Kostnad',
        x=[r['Scenario'] for r in stress_results],
        y=[r['Total kostnad'] for r in stress_results],
        marker_color=COLORS['danger']
    ))
    
    fig_stress.update_layout(
        title="Inntekt vs Kostnad i ulike scenarioer",
        yaxis_title="Kroner per måned",
        barmode='group',
        height=500
    )
    
    st.plotly_chart(fig_stress, use_container_width=True)
    
    # Anbefalinger basert på stress-test
    kritiske = sum(1 for r in stress_results if r['Margin før fradrag'] < 0)
    
    st.subheader("🎯 Anbefalinger")
    
    if kritiske == 0:
        st.success("""
        **Utmerket!** Økonomien deres tåler alle testede stress-scenarioer. 
        Dette er et trygt boligkjøp med god margin.
        """)
    elif kritiske <= 2:
        st.info("""
        **Akseptabel risiko.** Økonomien takler de fleste scenarioer, men vær oppmerksom på:
        - Ha minst 3-6 måneders utgifter i buffer
        - Vurder forsikringer (uføre, livsforsikring)
        - Følg nøye med på renteutviklingen
        """)
    else:
        st.warning("""
        **Høy risiko!** Flere stress-scenarioer gir negativ margin. Vurder:
        - Øke egenkapitalen
        - Se etter rimeligere bolig
        - Vente til inntektene øker
        - Ha minimum 6-12 måneders buffer
        """)

with tab5:
    st.header("Sammendrag og konklusjon")
    
    # Hovedtall
    st.subheader("📊 Hovedtall")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Boligpris", f"{boligpris:,.0f} kr")
        st.metric("Lånebeløp", f"{laanebelop:,.0f} kr")
    
    with col2:
        st.metric("Rente", f"{rente:.1f}%")
        st.metric("Terminbeløp", f"{terminbelop:,.0f} kr/mnd")
    
    with col3:
        st.metric("Skattefradrag", f"{skattefradrag_mnd:,.0f} kr/mnd",
                 help="22% av rentekostnader - kommer som økt nettoinntekt")
        st.metric("Total månedskostnad", f"{total_mnd_kostnad:,.0f} kr/mnd",
                 help="Faktisk månedlig utbetaling til bank og felleskostnader")
    
    with col4:
        avg_belastning = (belastning_a + belastning_b) / 2
        st.metric("Snitt belastning", f"{avg_belastning:.1f}%")
        total_disponibel = disponibel_etter_skatt_a + disponibel_etter_skatt_b
        st.metric("Total disponibel", f"{total_disponibel:,.0f} kr/mnd",
                 help="Totalt disponibelt beløp etter boligkostnader og skattefradrag")
    
    # Kostnadsfordeling pie chart
    st.subheader("💰 Månedlig kostnadsfordeling")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Kostnadskomponenter
        fig_pie = go.Figure(data=[go.Pie(
        labels=['Avdrag', 'Renter', 'Felleskostnader', 'Skattefradrag'],
        values=[avdrag_mnd, rentekostnad_mnd, felleskostnader, -skattefradrag_mnd],
        hole=.45,
        marker=dict(
            colors=[COLORS['success'], COLORS['warning'], COLORS['info'], COLORS['primary']],
            line=dict(color=COLORS['bg_card'], width=2)
        ),
        textfont=dict(size=12, color='rgba(0,0,0,0.8)'),
        textposition='auto',
        hovertemplate='<b>%{label}</b><br>%{value:,.0f} kr<br>%{percent}<extra></extra>'
    )])

    fig_pie.update_layout(
        title=dict(
            text="Kostnadskomponenter",
            font=dict(size=16, color=COLORS['text_primary'])
        ),
        height=350,
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="left",
            x=1.05,
            font=dict(color=COLORS['text_primary'])
        ),
        margin=dict(l=0, r=150, t=40, b=0),
        paper_bgcolor='rgba(0,0,0,0)',
        hoverlabel=dict(
            bgcolor=COLORS['bg_card'],
            font_color=COLORS['text_primary']
        )
    )

    # Total i midten med lys tekst
    fig_pie.add_annotation(
        text=f"<b>{total_mnd_kostnad:,.0f}<br>kr/mnd</b>",
        x=0.5, y=0.5,
        font=dict(size=14, color=COLORS['text_primary']),
        showarrow=False
    )

    st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        fig_fordeling = go.Figure(data=[
        go.Bar(
            name=navn_a, 
            x=['Kostnad', 'Inntekt'], 
            y=[kostnad_a, netto_mnd_a],
            text=[f'{kostnad_a:,.0f}', f'{netto_mnd_a:,.0f}'],
            textposition='outside',
            textfont=dict(color=COLORS['text_primary']),
            marker=dict(
                color=COLORS['person_a'],
                line=dict(color='rgba(129, 140, 248, 0.3)', width=1)
            ),
            hovertemplate='<b>%{fullData.name}</b><br>%{x}: %{y:,.0f} kr<extra></extra>'
        ),
        go.Bar(
            name=navn_b, 
            x=['Kostnad', 'Inntekt'], 
            y=[kostnad_b, netto_mnd_b],
            text=[f'{kostnad_b:,.0f}', f'{netto_mnd_b:,.0f}'],
            textposition='outside',
            textfont=dict(color=COLORS['text_primary']),
            marker=dict(
                color=COLORS['person_b'],
                line=dict(color='rgba(244, 114, 182, 0.3)', width=1)
            ),
            hovertemplate='<b>%{fullData.name}</b><br>%{x}: %{y:,.0f} kr<extra></extra>'
        )
    ])

    fig_fordeling.update_layout(
        title=dict(
            text="💰 Månedlig kostnad vs inntekt",
            font=dict(size=18, color=COLORS['text_primary'])
        ),
        yaxis=dict(
            title="Kroner",
            gridcolor=COLORS['light'],
            tickformat=",.0f",
            tickfont=dict(color=COLORS['text_secondary'])
            #titlefont=dict(color=COLORS['text_secondary'])
        ),
        xaxis=dict(
            gridcolor='rgba(0,0,0,0)',
            tickfont=dict(color=COLORS['text_secondary'])
        ),
        barmode='group',
        height=400,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(color=COLORS['text_primary'])
        ),
        bargap=0.15,
        bargroupgap=0.1,
        hoverlabel=dict(
            bgcolor=COLORS['bg_card'],
            font_color=COLORS['text_primary']
        )
    )

    st.plotly_chart(fig_fordeling, use_container_width=True)
    
    
    st.subheader("📈 Eierandel-utvikling over tid")

    # Beregn eierandel over tid basert på nedbetaling
    years = list(range(2025, 2025 + nedbetalingstid + 1))

    # Arrays for tracking
    eierandel_a_over_tid = []
    eierandel_b_over_tid = []
    total_nedbetalt = []
    gjenstaaende = []

    # Initial eierandel basert på egenkapital (i prosent av boligpris)
    initial_eierandel_a = (egenkapital_a / boligpris) * 100
    initial_eierandel_b = (egenkapital_b / boligpris) * 100

    # Start med egenkapital som basis for eierskap
    # Resterende eierskap (låneandelen) fordeles basert på hvem som betaler nedbetalingen

    # Total låneandel som skal fordeles
    total_laaneandel = (laanebelop / boligpris) * 100  # Dette er det som gjenstår å "kjøpe"

    # Beregn månedlig avdrag på lånet
    # For annuitetslån er avdraget lavt i starten og øker over tid
    # Men for enkelhet bruker vi gjennomsnittlig avdrag her
    gjennomsnittlig_maanedlig_avdrag = laanebelop / (nedbetalingstid * 12)
    aarlig_avdrag = gjennomsnittlig_maanedlig_avdrag * 12

    # Fordel fremtidig eierskap basert på betalingsfordeling
    if fordeling_type == "50/50":
        avdrag_andel_a = 0.5
    elif fordeling_type == "Proporsjonal etter inntekt":
        avdrag_andel_a = kostnad_a / (kostnad_a + kostnad_b) if (kostnad_a + kostnad_b) > 0 else 0.5
    else:  # Egendefinert
        avdrag_andel_a = custom_split / 100 if custom_split else 0.5

    avdrag_andel_b = 1 - avdrag_andel_a

    # Person A og B vil over tid "kjøpe" sin andel av låneandelen
    laaneandel_a = total_laaneandel * avdrag_andel_a  # Hvor mye av låneandelen A vil eie til slutt
    laaneandel_b = total_laaneandel * avdrag_andel_b  # Hvor mye av låneandelen B vil eie til slutt

    # Beregn utvikling år for år
    current_loan = laanebelop

    for i, year in enumerate(years):
        if i == 0:
            # Første år - kun egenkapital
            eierandel_a_over_tid.append(initial_eierandel_a)
            eierandel_b_over_tid.append(initial_eierandel_b)
            total_nedbetalt.append(0)
            gjenstaaende.append(laanebelop)
        else:
            # Beregn hvor mye som er nedbetalt så langt
            years_passed = i
            total_nedbetalt_saa_langt = min(aarlig_avdrag * years_passed, laanebelop)
            current_loan = laanebelop - total_nedbetalt_saa_langt
            
            # Beregn hvor stor andel av lånet som er nedbetalt
            prosent_nedbetalt = total_nedbetalt_saa_langt / laanebelop if laanebelop > 0 else 1
            
            # Legg til den nedbetalte andelen av lånet til eierandelen
            # Person A får sin andel av låneandelen basert på betalingsfordeling
            ekstra_eierandel_a = laaneandel_a * prosent_nedbetalt
            ekstra_eierandel_b = laaneandel_b * prosent_nedbetalt
            
            # Total eierandel = initial (fra EK) + opptjent (fra nedbetaling)
            total_eierandel_a = initial_eierandel_a + ekstra_eierandel_a
            total_eierandel_b = initial_eierandel_b + ekstra_eierandel_b
            
            eierandel_a_over_tid.append(total_eierandel_a)
            eierandel_b_over_tid.append(total_eierandel_b)
            total_nedbetalt.append(total_nedbetalt_saa_langt)
            gjenstaaende.append(current_loan)

    # Visualiser eierandel-utvikling
    fig_eierandel = go.Figure()

    # Stacked area chart for dark theme
    fig_eierandel.add_trace(go.Scatter(
        x=years,
        y=eierandel_a_over_tid,
        mode='lines',
        name=f'{navn_a}',
        fill='tonexty',
        stackgroup='one',
        line=dict(width=0.5, color=COLORS['person_a']),
        fillcolor=COLORS['person_a'],
        hovertemplate='<b>%{fullData.name}</b><br>År: %{x}<br>Eierandel: %{y:.1f}%<extra></extra>'
    ))

    fig_eierandel.add_trace(go.Scatter(
        x=years,
        y=eierandel_b_over_tid,
        mode='lines',
        name=f'{navn_b}',
        fill='tonexty',
        stackgroup='one',
        line=dict(width=0.5, color=COLORS['person_b']),
        fillcolor=COLORS['person_b'],
        hovertemplate='<b>%{fullData.name}</b><br>År: %{x}<br>Eierandel: %{y:.1f}%<extra></extra>'
    ))

    # 50% linje for dark theme
    fig_eierandel.add_shape(
        type="line",
        x0=years[0], x1=years[-1],
        y0=50, y1=50,
        line=dict(
            color=COLORS['text_muted'],
            width=1.5,
            dash="dash"
        )
    )

    fig_eierandel.add_annotation(
        x=years[-1],
        y=50,
        text="50% eierandel",
        showarrow=False,
        xanchor="left",
        xshift=10,
        font=dict(size=11, color=COLORS['text_muted'])
    )

    fig_eierandel.update_layout(
        title=dict(
            text=f"📈 Eierandel-utvikling over {nedbetalingstid} år",
            font=dict(size=20, color=COLORS['text_primary'])
        ),
        xaxis=dict(
            title="År",
            gridcolor=COLORS['light'],
            showgrid=True,
            tickfont=dict(color=COLORS['text_secondary'])
            #titlefont=dict(color=COLORS['text_secondary'])
        ),
        yaxis=dict(
            title="Eierandel (%)",
            range=[0, 100],
            gridcolor=COLORS['light'],
            showgrid=True,
            ticksuffix="%",
            tickfont=dict(color=COLORS['text_secondary'])
            #titlefont=dict(color=COLORS['text_secondary'])
        ),
        height=450,
        hovermode='x unified',
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            bgcolor='rgba(30, 41, 59, 0.8)',
            bordercolor=COLORS['light'],
            borderwidth=1,
            font=dict(color=COLORS['text_primary'])
        ),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        hoverlabel=dict(
            bgcolor=COLORS['bg_card'],
            font_color=COLORS['text_primary']
        )
    )

    st.plotly_chart(fig_eierandel, use_container_width=True)

    # Vis nøkkeltall for eierandel
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            f"Start eierandel {navn_a}", 
            f"{initial_eierandel_a:.1f}%",
            delta=f"+{eierandel_a_over_tid[-1] - initial_eierandel_a:.1f}%"
        )

    with col2:
        st.metric(
            f"Start eierandel {navn_b}", 
            f"{initial_eierandel_b:.1f}%",
            delta=f"+{eierandel_b_over_tid[-1] - initial_eierandel_b:.1f}%"
        )

    with col3:
        # Finn når lånet er 50% nedbetalt
        halvveis_aar = None
        for i, nedbetalt in enumerate(total_nedbetalt):
            if nedbetalt >= laanebelop / 2:
                halvveis_aar = years[i]
                break
        
        if halvveis_aar:
            st.metric("50% av lån nedbetalt", f"År {halvveis_aar}")
        else:
            st.metric("50% av lån nedbetalt", "Ikke innen periode")
    
    with st.expander("📊 Se detaljert nedbetalingsplan"):
        # Generer amortiseringsplan
        amortiseringsplan = beregn_amortiseringsplan(
            laanebelop, 
            rente, 
            nedbetalingstid,
            antall_aar=10  # Vis første 10 år
        )
        
        # Vis årlig sammendrag
        aarlig_sammendrag = amortiseringsplan.groupby('År').agg({
            'Terminbeløp': 'sum',
            'Renter': 'sum',
            'Avdrag': 'sum',
            'Skattefradrag': 'sum',
            'Netto kostnad': 'sum'
        }).round(0)

        st.markdown("**Årlig oversikt (første 10 år)**")
        st.dataframe(
            aarlig_sammendrag.style.format("{:,.0f} kr"),
            use_container_width=True
        )
        
        # Vis graf over rente vs avdrag
        fig_amortisering = go.Figure()
        
        # Månedlig data for graf
        fig_amortisering.add_trace(go.Scatter(
            x=list(range(len(amortiseringsplan))),
            y=amortiseringsplan['Avdrag'],
            name='Avdrag',
            fill='tonexty',
            stackgroup='one',
            line=dict(width=0),
            fillcolor=COLORS['success'],
            hovertemplate='Avdrag: %{y:,.0f} kr<extra></extra>'
        ))
        
        fig_amortisering.add_trace(go.Scatter(
            x=list(range(len(amortiseringsplan))),
            y=amortiseringsplan['Renter'],
            name='Renter',
            fill='tonexty',
            stackgroup='one',
            line=dict(width=0),
            fillcolor=COLORS['warning'],
            hovertemplate='Renter: %{y:,.0f} kr<extra></extra>'
        ))
        
        fig_amortisering.update_layout(
            title="Fordeling renter vs avdrag over tid",
            xaxis_title="Måneder",
            yaxis_title="Kroner",
            height=300,
            hovermode='x unified',
            showlegend=True,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color=COLORS['text_primary']),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="center",
                x=0.5
            )
        )
        
        st.plotly_chart(fig_amortisering, use_container_width=True)
        
        # Vis nøkkeltall
        col1, col2, col3 = st.columns(3)
        
        with col1:
            forste_aar_renter = amortiseringsplan[amortiseringsplan['År']==1]['Renter'].sum()
            forste_aar_avdrag = amortiseringsplan[amortiseringsplan['År']==1]['Avdrag'].sum()
            st.metric(
                "År 1 - Renteandel",
                f"{(forste_aar_renter/(forste_aar_renter+forste_aar_avdrag)*100):.1f}%"
            )
        
        with col2:
            if len(amortiseringsplan[amortiseringsplan['År']==5]) > 0:
                femte_aar_renter = amortiseringsplan[amortiseringsplan['År']==5]['Renter'].sum()
                femte_aar_avdrag = amortiseringsplan[amortiseringsplan['År']==5]['Avdrag'].sum()
                st.metric(
                    "År 5 - Renteandel",
                    f"{(femte_aar_renter/(femte_aar_renter+femte_aar_avdrag)*100):.1f}%"
                )
        
        with col3:
            total_renter_5_aar = amortiseringsplan['Renter'].sum()
            st.metric(
                "Totale renter (5 år)",
                f"{total_renter_5_aar:,.0f} kr"
            )
        
        st.info("""
        💡 **Hva viser dette?**
        - I starten går mesteparten til renter (typisk 70-80%)
        - Over tid øker avdragsandelen
        - Skattefradrag reduseres gradvis
        - Ekstra nedbetaling tidlig sparer mest renter
        """)

    # Vis slutt-eierandel tydeligere
    st.info(f"""
    **📊 Eierandel ved fullt nedbetalt lån ({2025 + nedbetalingstid}):**
    - {navn_a}: {eierandel_a_over_tid[-1]:.1f}%
    - {navn_b}: {eierandel_b_over_tid[-1]:.1f}%
    - **Totalt: {eierandel_a_over_tid[-1] + eierandel_b_over_tid[-1]:.1f}%**

    Fordelingen er basert på:
    1. Initial egenkapital: {navn_a} bidro med {egenkapital_a:,.0f} kr, {navn_b} med {egenkapital_b:,.0f} kr
    2. Nedbetalingsfordeling: {fordeling_type} {'(' + str(custom_split) + '/' + str(100-custom_split) + ')' if fordeling_type == 'Egendefinert' else ''}
    """)

    # Alternativer for eierandel
    st.subheader("🔄 Alternative eierandels-modeller")

    with st.expander("Se alternative modeller for eierskap"):
        st.markdown("""
        **1. Fast eierandel fra start (50/50 eller annet)**
        - Uavhengig av hvem som betaler hva
        - Krever at den som betaler mindre kompenserer ved salg
        - Enklest, men kan oppleves urettferdig
        
        **2. Proporsjonal etter total investering (dagens modell)**
        - Eierandel = (Egenkapital + Nedbetaling) / Total investering
        - Rettferdig fordeling basert på faktisk bidrag
        - Anbefales når bidragene er ulike
        
        **3. Egenkapital gir eierskap, lån deles likt**
        - Initial eierandel basert på egenkapital
        - Fremtidig eierskap (fra nedbetaling) deles 50/50
        - Balanserer initial investering med felles ansvar
        
        **4. Verdijustert modell**
        - Ta høyde for verdistigning/fall
        - Den som bidro med mest EK får større del av verdistigning
        - Mer komplekst, men kan være rettferdig ved stor verdistigning
        
        💡 **Viktig**: 
        - Dokumenter avtalen i samboeravtale eller ektepakt
        - Vurder hva som skjer ved salg, brudd, dødsfall
        - Konsulter gjerne advokat for juridisk bindende avtale
        """)

    # Sammenligning av modeller
    st.subheader("📊 Sammenligning av eierandels-modeller")

    # Beregn alternative modeller
    # Modell 1: 50/50 uansett
    modell1_a = 50
    modell1_b = 50

    # Modell 2: Dagens modell (allerede beregnet)
    modell2_a = eierandel_a_over_tid[-1]
    modell2_b = eierandel_b_over_tid[-1]

    # Modell 3: EK-basert + 50/50 på lån
    modell3_a = initial_eierandel_a + (total_laaneandel * 0.5)
    modell3_b = initial_eierandel_b + (total_laaneandel * 0.5)

    # Vis sammenligning
    sammenligning_data = {
        'Modell': ['50/50 fast', 'Proporsjonal (valgt)', 'EK + 50/50 lån'],
        f'{navn_a} (%)': [modell1_a, modell2_a, modell3_a],
        f'{navn_b} (%)': [modell1_b, modell2_b, modell3_b]
    }

    df_sammenligning = pd.DataFrame(sammenligning_data)

    # Vis som tabell med fargegradering
    st.dataframe(
        df_sammenligning.style.format({
            f'{navn_a} (%)': '{:.1f}',
            f'{navn_b} (%)': '{:.1f}'
        }).background_gradient(cmap='RdYlGn', vmin=30, vmax=70),
        use_container_width=True,
        hide_index=True
    )
    
    # Lagre scenario
    st.subheader("💾 Lagre scenario")

    scenario_navn = st.text_input("Gi scenarioet et navn", placeholder="F.eks. 'Leilighet Grünerløkka'", key="scenario_navn")
    
    if st.button("Lagre scenario", type="primary"):
        if scenario_navn:
            scenario_data = {
                'navn': scenario_navn,
                'timestamp': datetime.now().isoformat(),
                'boligpris': boligpris,
                'egenkapital': egenkapital,
                'rente': rente,
                'nedbetalingstid': nedbetalingstid,
                'felleskostnader': felleskostnader,
                'inntekt_a': brutto_aar_a,
                'inntekt_b': brutto_aar_b,
                'fordeling_type': fordeling_type,
                'total_kostnad': total_mnd_kostnad,
                'kostnad_a': kostnad_a,
                'kostnad_b': kostnad_b,
                'belastning_a': belastning_a,
                'belastning_b': belastning_b
            }
            
            st.session_state.scenarios.append(scenario_data)
            st.success(f"✅ Scenario '{scenario_navn}' lagret!")
            st.balloons()
        else:
            st.error("Vennligst gi scenarioet et navn")
    
    # Eksporter til clipboard
    if st.button("📋 Kopier sammendrag"):
        summary = f"""
BOLIGKJØP - ØKONOMISK ANALYSE
{'='*40}
Eiendom: {scenario_navn if scenario_navn else 'Ikke navngitt'}
Kjøpesum: {boligpris:,.0f} kr
Lånebeløp: {laanebelop:,.0f} kr
Rente: {rente}%

MÅNEDLIGE KOSTNADER
{'-'*40}
Terminbeløp: {terminbelop:,.0f} kr
Felleskostnader: {felleskostnader:,.0f} kr
Skattefradrag: -{skattefradrag_mnd:,.0f} kr
TOTAL: {total_mnd_kostnad:,.0f} kr

FORDELING
{'-'*40}
{navn_a}: {kostnad_a:,.0f} kr ({belastning_a:.1f}% av inntekt)
{navn_b}: {kostnad_b:,.0f} kr ({belastning_b:.1f}% av inntekt)

VURDERING
{'-'*40}
{'✅ Bærekraftig' if avg_belastning < 30 else '⚠️ Høy belastning' if avg_belastning < 35 else '❌ Risikabelt'}
Gjennomsnittlig belastningsgrad: {avg_belastning:.1f}%
Total disponibel inntekt: {total_disponibel:,.0f} kr/mnd
        """
        st.code(summary, language='text')
        st.info("Merk teksten over og kopier (Ctrl+C / Cmd+C)")


with tab6:
    st.header("💪 Bærekraftighet og personlig økonomi")
    
    st.markdown("""
    Analyser deres personlige økonomi etter boligkjøp, inkludert alle utgifter og gjeld.
    Dette gir et realistisk bilde av økonomisk handlingsrom.
    """)
    
    # Personlig gjeld og utgifter
    st.subheader("📋 Eksisterende gjeld og faste utgifter")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"### {navn_a}")
        
        studielaan_a = st.number_input(
            "Studielån (kr/mnd)",
            min_value=0,
            max_value=20000,
            value=2900,
            step=500,
            key="studielaan_a",
            help="Månedlig betaling på studielån"
        )
        
        billaan_a = st.number_input(
            "Billån/leasing (kr/mnd)",
            min_value=0,
            max_value=20000,
            value=0,
            step=500,
            key="billaan_a"
        )
        
        annen_gjeld_a = st.number_input(
            "Annen gjeld (kr/mnd)",
            min_value=0,
            max_value=20000,
            value=0,
            step=500,
            key="annen_gjeld_a",
            help="Kredittkort, forbrukslån, etc."
        )
        
        # Personlige utgifter
        st.markdown("**Personlige utgifter**")
        
        mat_a = st.number_input(
            "Mat/dagligvarer (kr/mnd)",
            min_value=0,
            max_value=15000,
            value=4000,
            step=500,
            key="mat_a"
        )
        
        transport_a = st.number_input(
            "Transport (kr/mnd)",
            min_value=0,
            max_value=10000,
            value=1500,
            step=500,
            key="transport_a",
            help="Kollektiv, bensin, etc."
        )
        
        diverse_a = st.number_input(
            "Diverse/underholdning (kr/mnd)",
            min_value=0,
            max_value=20000,
            value=5000,
            step=500,
            key="diverse_a",
            help="Klær, trening, streaming, etc."
        )
    
    with col2:
        st.markdown(f"### {navn_b}")
        
        studielaan_b = st.number_input(
            "Studielån (kr/mnd)",
            min_value=0,
            max_value=20000,
            value=3100,
            step=500,
            key="studielaan_b",
            help="Månedlig betaling på studielån"
        )
        
        billaan_b = st.number_input(
            "Billån/leasing (kr/mnd)",
            min_value=0,
            max_value=20000,
            value=0,
            step=500,
            key="billaan_b"
        )
        
        annen_gjeld_b = st.number_input(
            "Annen gjeld (kr/mnd)",
            min_value=0,
            max_value=20000,
            value=0,
            step=500,
            key="annen_gjeld_b",
            help="Kredittkort, forbrukslån, etc."
        )
        
        # Personlige utgifter
        st.markdown("**Personlige utgifter**")
        
        mat_b = st.number_input(
            "Mat/dagligvarer (kr/mnd)",
            min_value=0,
            max_value=15000,
            value=6500,
            step=500,
            key="mat_b"
        )
        
        transport_b = st.number_input(
            "Transport (kr/mnd)",
            min_value=0,
            max_value=10000,
            value=2000,
            step=500,
            key="transport_b",
            help="Kollektiv, bensin, etc."
        )
        
        diverse_b = st.number_input(
            "Diverse/underholdning (kr/mnd)",
            min_value=0,
            max_value=20000,
            value=5000,
            step=500,
            key="diverse_b",
            help="Klær, trening, streaming, etc."
        )
    
    # Felles utgifter
    st.subheader("🏠 Felles boligutgifter (utenom lån)")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        strom = st.number_input(
            "Strøm (kr/mnd)",
            min_value=0,
            max_value=5000,
            value=1500,
            step=100
        )
        
        internett = st.number_input(
            "Internett/TV (kr/mnd)",
            min_value=0,
            max_value=2000,
            value=800,
            step=100
        )
    
    with col2:
        forsikring = st.number_input(
            "Forsikringer (kr/mnd)",
            min_value=0,
            max_value=5000,
            value=1200,
            step=100,
            help="Innbo, bolig, etc."
        )
        
        vedlikehold = st.number_input(
            "Vedlikehold/buffer (kr/mnd)",
            min_value=0,
            max_value=5000,
            value=1000,
            step=100
        )
    
    with col3:
        kommunale_avg = st.number_input(
            "Kommunale avgifter (kr/mnd)",
            min_value=0,
            max_value=3000,
            value=800,
            step=100
        )
        
        andre_felles = st.number_input(
            "Andre felles (kr/mnd)",
            min_value=0,
            max_value=5000,
            value=0,
            step=100
        )
    
    # Beregninger
    st.markdown("---")
    st.subheader("📊 Økonomisk oversikt etter boligkjøp")
    
    # Totale utgifter per person
    total_gjeld_a = studielaan_a + billaan_a + annen_gjeld_a
    total_gjeld_b = studielaan_b + billaan_b + annen_gjeld_b
    
    personlige_utgifter_a = mat_a + transport_a + diverse_a
    personlige_utgifter_b = mat_b + transport_b + diverse_b
    
    totale_felles_utgifter = strom + internett + forsikring + vedlikehold + kommunale_avg + andre_felles
    
    # Fordel felles utgifter (kan bruke samme fordelingsmodell som boliglån)
    if fordeling_type == "50/50":
        felles_fordelt_a = totale_felles_utgifter / 2
        felles_fordelt_b = totale_felles_utgifter / 2
    elif fordeling_type == "Proporsjonal etter inntekt":
        andel_a = brutto_aar_a / (brutto_aar_a + brutto_aar_b) if (brutto_aar_a + brutto_aar_b) > 0 else 0.5
        felles_fordelt_a = totale_felles_utgifter * andel_a
        felles_fordelt_b = totale_felles_utgifter * (1 - andel_a)
    else:  # Egendefinert
        andel_a = custom_split / 100 if custom_split else 0.5
        felles_fordelt_a = totale_felles_utgifter * andel_a
        felles_fordelt_b = totale_felles_utgifter * (1 - andel_a)
    
    # Totale månedlige utgifter
    total_utgifter_a = kostnad_a + total_gjeld_a + personlige_utgifter_a + felles_fordelt_a
    total_utgifter_b = kostnad_b + total_gjeld_b + personlige_utgifter_b + felles_fordelt_b
    
    # Disponibelt etter alle utgifter
    disponibelt_etter_alt_a = netto_mnd_a - total_utgifter_a
    disponibelt_etter_alt_b = netto_mnd_b - total_utgifter_b
    
    # Vis resultater
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"### 💼 {navn_a}")
        
        # Inntekt
        st.metric("Netto månedsinntekt", f"{netto_mnd_a:,.0f} kr")
        
        # Utgifter breakdown
        st.markdown("**Utgifter:**")
        utgifter_data_a = {
            "Boliglån": kostnad_a,
            "Studielån": studielaan_a,
            "Billån": billaan_a,
            "Annen gjeld": annen_gjeld_a,
            "Mat/dagligvarer": mat_a,
            "Transport": transport_a,
            "Diverse": diverse_a,
            "Felles bolig": felles_fordelt_a
        }
        
        for kategori, belop in utgifter_data_a.items():
            if belop > 0:
                st.caption(f"{kategori}: {belop:,.0f} kr")
        
        st.markdown("**Oppsummering:**")
        st.metric("Totale utgifter", f"{total_utgifter_a:,.0f} kr")
        
        if disponibelt_etter_alt_a >= 0:
            st.metric("✅ Disponibelt", f"{disponibelt_etter_alt_a:,.0f} kr", 
                     delta=f"{(disponibelt_etter_alt_a/netto_mnd_a*100):.1f}% av inntekt")
        else:
            st.metric("❌ Underskudd", f"{disponibelt_etter_alt_a:,.0f} kr", 
                     delta="Ikke bærekraftig!")
        
        # Spareevne
        spareevne_a = (disponibelt_etter_alt_a / netto_mnd_a * 100) if netto_mnd_a > 0 else 0
        if spareevne_a > 20:
            st.success(f"Utmerket spareevne: {spareevne_a:.1f}%")
        elif spareevne_a > 10:
            st.info(f"God spareevne: {spareevne_a:.1f}%")
        elif spareevne_a > 0:
            st.warning(f"Begrenset spareevne: {spareevne_a:.1f}%")
        else:
            st.error("Ingen spareevne - vurder å redusere utgifter")
    
    with col2:
        st.markdown(f"### 💼 {navn_b}")
        
        # Inntekt
        st.metric("Netto månedsinntekt", f"{netto_mnd_b:,.0f} kr")
        
        # Utgifter breakdown
        st.markdown("**Utgifter:**")
        utgifter_data_b = {
            "Boliglån": kostnad_b,
            "Studielån": studielaan_b,
            "Billån": billaan_b,
            "Annen gjeld": annen_gjeld_b,
            "Mat/dagligvarer": mat_b,
            "Transport": transport_b,
            "Diverse": diverse_b,
            "Felles bolig": felles_fordelt_b
        }
        
        for kategori, belop in utgifter_data_b.items():
            if belop > 0:
                st.caption(f"{kategori}: {belop:,.0f} kr")
        
        st.markdown("**Oppsummering:**")
        st.metric("Totale utgifter", f"{total_utgifter_b:,.0f} kr")
        
        if disponibelt_etter_alt_b >= 0:
            st.metric("✅ Disponibelt", f"{disponibelt_etter_alt_b:,.0f} kr", 
                     delta=f"{(disponibelt_etter_alt_b/netto_mnd_b*100):.1f}% av inntekt")
        else:
            st.metric("❌ Underskudd", f"{disponibelt_etter_alt_b:,.0f} kr", 
                     delta="Ikke bærekraftig!")
        
        # Spareevne
        spareevne_b = (disponibelt_etter_alt_b / netto_mnd_b * 100) if netto_mnd_b > 0 else 0
        if spareevne_b > 20:
            st.success(f"Utmerket spareevne: {spareevne_b:.1f}%")
        elif spareevne_b > 10:
            st.info(f"God spareevne: {spareevne_b:.1f}%")
        elif spareevne_b > 0:
            st.warning(f"Begrenset spareevne: {spareevne_b:.1f}%")
        else:
            st.error("Ingen spareevne - vurder å redusere utgifter")
    
    # Visualisering av utgiftsfordeling
    st.subheader("📊 Visualisering av økonomi")
    
    # Sammenligning av utgifter
    fig_utgifter = go.Figure()
    
    kategorier = ['Boliglån', 'Gjeld', 'Mat', 'Transport', 'Diverse', 'Felles', 'Disponibelt']
    
    verdier_a = [
        kostnad_a,
        total_gjeld_a,
        mat_a,
        transport_a,
        diverse_a,
        felles_fordelt_a,
        max(0, disponibelt_etter_alt_a)
    ]
    
    verdier_b = [
        kostnad_b,
        total_gjeld_b,
        mat_b,
        transport_b,
        diverse_b,
        felles_fordelt_b,
        max(0, disponibelt_etter_alt_b)
    ]
    
    fig_utgifter.add_trace(go.Bar(
        name=navn_a,
        x=kategorier,
        y=verdier_a,
        text=[f'{v:,.0f}' for v in verdier_a],
        textposition='auto',
    ))
    
    fig_utgifter.add_trace(go.Bar(
        name=navn_b,
        x=kategorier,
        y=verdier_b,
        text=[f'{v:,.0f}' for v in verdier_b],
        textposition='auto',
    ))
    
    fig_utgifter.update_layout(
        title="Månedlig økonomi etter alle utgifter",
        yaxis_title="Kroner",
        barmode='group',
        height=400
    )
    
    st.plotly_chart(fig_utgifter, use_container_width=True)
    
    # Total økonomi som par
    st.subheader("👫 Samlet økonomi")
    
    total_netto = netto_mnd_a + netto_mnd_b
    total_utgifter = total_utgifter_a + total_utgifter_b
    total_disponibelt = disponibelt_etter_alt_a + disponibelt_etter_alt_b
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total inntekt", f"{total_netto:,.0f} kr/mnd")
    with col2:
        st.metric("Totale utgifter", f"{total_utgifter:,.0f} kr/mnd")
    with col3:
        st.metric("Disponibelt sammen", f"{total_disponibelt:,.0f} kr/mnd")
    with col4:
        samlet_spareevne = (total_disponibelt / total_netto * 100) if total_netto > 0 else 0
        st.metric("Spareevne", f"{samlet_spareevne:.1f}%")
    
    # Anbefalinger
    st.markdown("---")
    st.subheader("💡 Anbefalinger")
    
    if total_disponibelt < 5000:
        st.error("""
        **⚠️ Svært begrenset økonomi**
        - Lite rom for uforutsette utgifter
        - Vurder å redusere boligpris eller øke inntekter
        - Se over alle utgiftsposter for mulige kutt
        """)
    elif total_disponibelt < 10000:
        st.warning("""
        **⚠️ Stram økonomi**
        - Begrenset buffer for uforutsette utgifter
        - Anbefaler å bygge opp sparebuffer
        - Vær forsiktig med ytterligere gjeld
        """)
    elif total_disponibelt < 20000:
        st.info("""
        **✅ Akseptabel økonomi**
        - Rom for sparing og buffer
        - Fortsett å følge budsjett
        - Bygg opp 3-6 måneders buffer
        """)
    else:
        st.success("""
        **🎉 Solid økonomi**
        - God spareevne og handlingsrom
        - Vurder ekstra nedbetaling av lån
        - God buffer for fremtidige planer
        """)

with tab7:
    st.header("💸 Salgsgevinst og verdiøkning")
    
    st.markdown("""
    Analyser hvordan gevinst fordeles ved salg før lånet er nedbetalt.
    Bruker nøyaktig amortiseringsplan for korrekte beregninger.
    """)
    
    # Input for salgsscenario
    st.subheader("🏷️ Salgsscenario")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        salgsaar = st.slider(
            "År etter kjøp",
            min_value=1,
            max_value=min(nedbetalingstid, 30),
            value=min(5, nedbetalingstid),
            help="Når planlegger dere å selge?",
            key="salgsaar"
        )

    with col2:
        verdiendring_prosent = st.number_input(
            "Forventet verdiendring (%)",
            min_value=-30.0,
            max_value=100.0,
            value=33.3,
            step=5.0,
            help="Positiv = verdistigning, Negativ = verdifall",
            key="verdiendring_prosent"
        )

    with col3:
        salgskostnader_prosent = st.number_input(
            "Salgskostnader (%)",
            min_value=0.0,
            max_value=10.0,
            value=2.5,
            step=0.5,
            help="Megler, markedsføring, etc.",
            key="salgskostnader_prosent"
        )
    
    # NØYAKTIG BEREGNING MED AMORTISERINGSPLAN
    st.markdown("---")
    st.subheader("📊 Nøyaktig nedbetalingsanalyse")
    
    # Generer amortiseringsplan
    amortiseringsplan = beregn_amortiseringsplan(laanebelop, rente, nedbetalingstid, salgsaar)
    
    # Initialiser verdier (fallback hvis amortiseringsplan feiler)
    total_avdrag = 0
    total_renter = 0
    total_skattefradrag = 0
    gjenstaaende_laan = laanebelop
    
    if not amortiseringsplan.empty:
        # Beregn nøyaktige tall basert på amortiseringsplan
        total_avdrag = amortiseringsplan['Avdrag'].sum()
        total_renter = amortiseringsplan['Renter'].sum()
        total_skattefradrag = amortiseringsplan['Skattefradrag'].sum()
        gjenstaaende_laan = laanebelop - total_avdrag
        
        # Vis nøkkeltall
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                f"Nedbetalt etter {salgsaar} år",
                f"{total_avdrag:,.0f} kr",
                delta=f"{(total_avdrag/laanebelop*100):.1f}% av lån"
            )
        
        with col2:
            st.metric(
                "Gjenstående lån",
                f"{gjenstaaende_laan:,.0f} kr",
                delta=f"{(gjenstaaende_laan/laanebelop*100):.1f}% gjenstår"
            )
        
        with col3:
            st.metric(
                "Totalt betalt renter",
                f"{total_renter:,.0f} kr",
                help=f"Skattefradrag: {total_skattefradrag:,.0f} kr"
            )
        
        with col4:
            andel_til_renter = (total_renter / (total_renter + total_avdrag) * 100) if (total_renter + total_avdrag) > 0 else 0
            st.metric(
                "Andel gått til renter",
                f"{andel_til_renter:.1f}%",
                delta="Resten til avdrag"
            )
        
        # Vis amortiseringsplan i ekspander
        with st.expander(f"📋 Se detaljert nedbetalingsplan (første {salgsaar} år)"):
            # Årlig sammendrag
            aarlig_sammendrag = amortiseringsplan.groupby('År').agg({
                'Terminbeløp': 'sum',
                'Renter': 'sum',
                'Avdrag': 'sum',
                'Skattefradrag': 'sum',
                'Gjenstående': 'last'
            }).round(0)
            
            st.dataframe(
                aarlig_sammendrag.style.format({
                    'Terminbeløp': '{:,.0f} kr',
                    'Renter': '{:,.0f} kr',
                    'Avdrag': '{:,.0f} kr',
                    'Skattefradrag': '{:,.0f} kr',
                    'Gjenstående': '{:,.0f} kr'
                }).background_gradient(subset=['Avdrag'], cmap='Greens'),
                use_container_width=True
            )
            
            # Graf over rente vs avdrag
            fig_amortisering = go.Figure()
            
            # Årlige data for graf
            aarlig_for_graf = amortiseringsplan.groupby('År').agg({
                'Avdrag': 'sum',
                'Renter': 'sum'
            })
            
            fig_amortisering.add_trace(go.Bar(
                x=aarlig_for_graf.index,
                y=aarlig_for_graf['Avdrag'],
                name='Avdrag',
                marker=dict(color=COLORS['success']),
                text=[f"{v:,.0f}" for v in aarlig_for_graf['Avdrag']],
                textposition='inside',
                textfont=dict(size=10),
                hovertemplate='År %{x}<br>Avdrag: %{y:,.0f} kr<extra></extra>'
            ))
            
            fig_amortisering.add_trace(go.Bar(
                x=aarlig_for_graf.index,
                y=aarlig_for_graf['Renter'],
                name='Renter',
                marker=dict(color=COLORS['warning']),
                text=[f"{v:,.0f}" for v in aarlig_for_graf['Renter']],
                textposition='inside',
                textfont=dict(size=10),
                hovertemplate='År %{x}<br>Renter: %{y:,.0f} kr<extra></extra>'
            ))
            
            fig_amortisering.update_layout(
                title="Årlig fordeling: Renter vs Avdrag",
                xaxis_title="År",
                yaxis_title="Kroner",
                barmode='stack',
                height=350,
                showlegend=True,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color=COLORS['text_primary']),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="center",
                    x=0.5
                )
            )
            
            st.plotly_chart(fig_amortisering, use_container_width=True)
    else:
        # Fallback hvis amortiseringsplan feiler
        st.warning("Bruker forenklet beregning")
        total_avdrag = (laanebelop / nedbetalingstid) * salgsaar
        gjenstaaende_laan = laanebelop - total_avdrag
    
    # BEREGN SALGSOPPGJØR MED NØYAKTIGE TALL
    st.markdown("---")
    st.subheader("💰 Salgsoppgjør")
    
    # Beregn verdier ved salg
    salgspris = boligpris * (1 + verdiendring_prosent / 100)
    verdiendring_kr = salgspris - boligpris
    salgskostnader = salgspris * (salgskostnader_prosent / 100)
    
    # Netto fra salg
    netto_salgssum = salgspris - salgskostnader - gjenstaaende_laan
    
    # Vis oversikt
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Salgspris", f"{salgspris:,.0f} kr")
        st.caption(f"Verdiendring: {verdiendring_kr:+,.0f} kr")
    
    with col2:
        st.metric("Gjenstående lån", f"{gjenstaaende_laan:,.0f} kr")
        st.caption(f"Nedbetalt: {total_avdrag:,.0f} kr")
    
    with col3:
        st.metric("Salgskostnader", f"{salgskostnader:,.0f} kr")
        st.caption(f"{salgskostnader_prosent}% av salgspris")
    
    with col4:
        st.metric("Netto ved salg", f"{netto_salgssum:,.0f} kr")
        roi = ((netto_salgssum - egenkapital) / egenkapital * 100) if egenkapital > 0 else 0
        st.caption(f"ROI på EK: {roi:+.1f}%")
    
    # BEREGN NØYAKTIG EIERANDEL PÅ SALGSTIDSPUNKTET
    st.markdown("---")
    st.subheader("📊 Eierandel ved salg")
    
    # Fordel avdrag basert på betalingsfordeling
    if fordeling_type == "50/50":
        nedbetalt_a = total_avdrag * 0.5
        nedbetalt_b = total_avdrag * 0.5
    elif fordeling_type == "Proporsjonal etter inntekt":
        andel_a = kostnad_a / (kostnad_a + kostnad_b) if (kostnad_a + kostnad_b) > 0 else 0.5
        nedbetalt_a = total_avdrag * andel_a
        nedbetalt_b = total_avdrag * (1 - andel_a)
    else:  # Egendefinert
        andel_a = custom_split / 100 if custom_split else 0.5
        nedbetalt_a = total_avdrag * andel_a
        nedbetalt_b = total_avdrag * (1 - andel_a)
    
    # Total investering per person (nøyaktig)
    total_investert_a = egenkapital_a + nedbetalt_a
    total_investert_b = egenkapital_b + nedbetalt_b
    total_investert = total_investert_a + total_investert_b
    
    # Vis investering og eierandel
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"**{navn_a}**")
        st.metric("Egenkapital", f"{egenkapital_a:,.0f} kr")
        st.metric("Nedbetalt", f"{nedbetalt_a:,.0f} kr")
        st.metric(
            "Total investert",
            f"{total_investert_a:,.0f} kr",
            delta=f"{(total_investert_a/total_investert*100):.1f}% eierandel"
        )
    
    with col2:
        st.markdown(f"**{navn_b}**")
        st.metric("Egenkapital", f"{egenkapital_b:,.0f} kr")
        st.metric("Nedbetalt", f"{nedbetalt_b:,.0f} kr")
        st.metric(
            "Total investert",
            f"{total_investert_b:,.0f} kr",
            delta=f"{(total_investert_b/total_investert*100):.1f}% eierandel"
        )
    
    # ULIKE FORDELINGSMODELLER
    st.markdown("---")
    st.subheader("🔄 Fordelingsmodeller for gevinst")
    
    fordelingsmodell = st.radio(
        "Velg hvordan gevinsten skal fordeles:",
        [
            "Modell 1: Proporsjonal etter total investering",
            "Modell 2: Proporsjonal etter egenkapital", 
            "Modell 3: 50/50 på gevinst",
            "Modell 4: Hybrid (EK-proporsjonal på gevinst, investering på tap)"
        ]
    )
    
    # Beregn fordeling basert på valgt modell
    if "Modell 1" in fordelingsmodell:
        # Proporsjonal etter total investering
        andel_a = total_investert_a / total_investert if total_investert > 0 else 0.5
        andel_b = total_investert_b / total_investert if total_investert > 0 else 0.5
        
        utbetaling_a = netto_salgssum * andel_a
        utbetaling_b = netto_salgssum * andel_b
        
        modell_beskrivelse = """
        **Modell 1: Proporsjonal etter total investering** (Anbefalt)
        - Fordeler alt basert på total investering (egenkapital + nedbetaling)
        - Mest rettferdig når begge bidrar til nedbetaling
        - Gevinst og tap fordeles likt
        """
        
    elif "Modell 2" in fordelingsmodell:
        # Proporsjonal etter egenkapital
        ek_andel_a = egenkapital_a / egenkapital if egenkapital > 0 else 0.5
        ek_andel_b = egenkapital_b / egenkapital if egenkapital > 0 else 0.5
        
        if netto_salgssum > total_investert:
            gevinst = netto_salgssum - total_investert
            utbetaling_a = total_investert_a + (gevinst * ek_andel_a)
            utbetaling_b = total_investert_b + (gevinst * ek_andel_b)
        else:
            utbetaling_a = netto_salgssum * (total_investert_a / total_investert) if total_investert > 0 else netto_salgssum * 0.5
            utbetaling_b = netto_salgssum * (total_investert_b / total_investert) if total_investert > 0 else netto_salgssum * 0.5
        
        modell_beskrivelse = """
        **Modell 2: Proporsjonal etter egenkapital**
        - Investering tilbakebetales først
        - Gevinst fordeles basert på initial egenkapital
        - Belønner den som bidro med mest egenkapital
        """
        
    elif "Modell 3" in fordelingsmodell:
        # 50/50 på gevinst
        if netto_salgssum > total_investert:
            gevinst = netto_salgssum - total_investert
            utbetaling_a = total_investert_a + (gevinst * 0.5)
            utbetaling_b = total_investert_b + (gevinst * 0.5)
        else:
            utbetaling_a = netto_salgssum * (total_investert_a / total_investert) if total_investert > 0 else netto_salgssum * 0.5
            utbetaling_b = netto_salgssum * (total_investert_b / total_investert) if total_investert > 0 else netto_salgssum * 0.5
        
        modell_beskrivelse = """
        **Modell 3: 50/50 på gevinst**
        - Investering tilbakebetales først
        - Gevinst deles likt uavhengig av bidrag
        - Enkel, men kan være urettferdig
        """
        
    else:  # Hybrid
        if verdiendring_kr > 0:
            # Ved gevinst: fordel etter egenkapital
            ek_andel_a = egenkapital_a / egenkapital if egenkapital > 0 else 0.5
            ek_andel_b = egenkapital_b / egenkapital if egenkapital > 0 else 0.5
            
            if netto_salgssum > total_investert:
                gevinst = netto_salgssum - total_investert
                utbetaling_a = total_investert_a + (gevinst * ek_andel_a)
                utbetaling_b = total_investert_b + (gevinst * ek_andel_b)
            else:
                utbetaling_a = netto_salgssum * (total_investert_a / total_investert) if total_investert > 0 else netto_salgssum * 0.5
                utbetaling_b = netto_salgssum * (total_investert_b / total_investert) if total_investert > 0 else netto_salgssum * 0.5
        else:
            # Ved tap: fordel etter total investering
            andel_a = total_investert_a / total_investert if total_investert > 0 else 0.5
            andel_b = total_investert_b / total_investert if total_investert > 0 else 0.5
            
            utbetaling_a = netto_salgssum * andel_a
            utbetaling_b = netto_salgssum * andel_b
        
        modell_beskrivelse = """
        **Modell 4: Hybrid**
        - Ved gevinst: Fordeles etter egenkapital
        - Ved tap: Fordeles etter total investering
        - Balanserer risiko og belønning
        """
    
    # Vis modellbeskrivelse
    st.info(modell_beskrivelse)
    
    # Vis resultat
    st.markdown("### 💰 Fordeling ved salg")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"#### {navn_a}")
        st.metric("Investert totalt", f"{total_investert_a:,.0f} kr")
        st.metric("Utbetaling ved salg", f"{utbetaling_a:,.0f} kr")
        
        gevinst_a = utbetaling_a - total_investert_a
        if gevinst_a >= 0:
            st.metric("✅ Gevinst", f"{gevinst_a:,.0f} kr", 
                     delta=f"{(gevinst_a/total_investert_a*100):.1f}% avkastning")
        else:
            st.metric("❌ Tap", f"{gevinst_a:,.0f} kr",
                     delta=f"{(gevinst_a/total_investert_a*100):.1f}% tap")
    
    with col2:
        st.markdown(f"#### {navn_b}")
        st.metric("Investert totalt", f"{total_investert_b:,.0f} kr")
        st.metric("Utbetaling ved salg", f"{utbetaling_b:,.0f} kr")
        
        gevinst_b = utbetaling_b - total_investert_b
        if gevinst_b >= 0:
            st.metric("✅ Gevinst", f"{gevinst_b:,.0f} kr",
                     delta=f"{(gevinst_b/total_investert_b*100):.1f}% avkastning")
        else:
            st.metric("❌ Tap", f"{gevinst_b:,.0f} kr",
                     delta=f"{(gevinst_b/total_investert_b*100):.1f}% tap")
    
    # VISUALISERING AV PENGESTRØM
    st.markdown("### 📊 Visualisering av pengestrøm")

    fig_waterfall = go.Figure()

    # Data for waterfall
    x_labels = ['Salgspris', 'Salgskostnader', 'Tilbakebetale lån', 'Netto ved salg', 
                f'{navn_a} får', f'{navn_b} får']
    y_values = [salgspris, -salgskostnader, -gjenstaaende_laan, 0, 
                -utbetaling_a, -utbetaling_b]

    # Beregn kumulative verdier
    cumulative = []
    running_total = 0
    for val in y_values:
        if val != 0:
            cumulative.append(running_total + val)
            running_total += val
        else:
            cumulative.append(running_total)

    # Lag waterfall for dark theme
    for i in range(len(x_labels)):
        if i == 0:
            # Salgspris - positiv start
            fig_waterfall.add_trace(go.Bar(
                x=[x_labels[i]],
                y=[y_values[i]],
                name='Salgspris',
                marker=dict(
                    color=COLORS['success'],
                    line=dict(color='rgba(52, 211, 153, 0.3)', width=1)
                ),
                text=f"<b>{y_values[i]:,.0f} kr</b>",
                textposition='outside',
                textfont=dict(size=11, color=COLORS['text_primary'])
            ))
        elif i == 1 or i == 2:
            # Kostnader - negative
            fig_waterfall.add_trace(go.Bar(
                x=[x_labels[i]],
                y=[abs(y_values[i])],
                base=cumulative[i] if y_values[i] < 0 else cumulative[i-1],
                name=x_labels[i],
                marker=dict(
                    color=COLORS['danger'] if i == 1 else COLORS['warning'],
                    line=dict(color='rgba(0,0,0,0.2)', width=1)
                ),
                text=f"{abs(y_values[i]):,.0f} kr",
                textposition='inside',
                textfont=dict(size=11, color='rgba(0,0,0,0.8)')
            ))
        elif i == 3:
            # Netto resultat
            fig_waterfall.add_trace(go.Bar(
                x=[x_labels[i]],
                y=[cumulative[i-1]],
                name='Netto',
                marker=dict(
                    color=COLORS['primary'],
                    line=dict(color='rgba(167, 139, 250, 0.5)', width=2),
                    pattern=dict(shape="/", size=4, solidity=0.2)
                ),
                text=f"<b>{cumulative[i-1]:,.0f} kr</b>",
                textposition='outside',
                textfont=dict(size=12, color=COLORS['text_primary'])
            ))
        else:
            # Person A og B sin andel
            person_color = COLORS['person_a'] if navn_a in x_labels[i] else COLORS['person_b']
            fig_waterfall.add_trace(go.Bar(
                x=[x_labels[i]],
                y=[abs(y_values[i])],
                base=cumulative[i] if y_values[i] < 0 else cumulative[i-1],
                name=x_labels[i],
                marker=dict(
                    color=person_color,
                    line=dict(color='rgba(0,0,0,0.2)', width=1)
                ),
                text=f"{abs(y_values[i]):,.0f} kr",
                textposition='inside',
                textfont=dict(size=11, color='rgba(0,0,0,0.8)')
            ))

    fig_waterfall.update_layout(
        title=dict(
            text="💰 Pengestrøm ved salg",
            font=dict(size=20, color=COLORS['text_primary'])
        ),
        yaxis=dict(
            title="Kroner",
            gridcolor=COLORS['light'],
            tickformat=",.0f",
            tickfont=dict(color=COLORS['text_secondary'])
            #titlefont=dict(color=COLORS['text_secondary'])
        ),
        xaxis=dict(
            gridcolor='rgba(0,0,0,0)',
            tickfont=dict(color=COLORS['text_secondary'])
        ),
        showlegend=False,
        height=450,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        hoverlabel=dict(
            bgcolor=COLORS['bg_card'],
            font_size=12,
            font_family="Arial",
            font_color=COLORS['text_primary']
        ),
        margin=dict(t=60, b=40)
    )

    st.plotly_chart(fig_waterfall, use_container_width=True)
    
    # SCENARIO-ANALYSE
    st.markdown("---")
    st.subheader("📈 Scenario-analyse")
    
    # Lag tabell med ulike verdiutviklinger
    scenarios = [
        ("Kraftig fall", -20),
        ("Moderat fall", -10),
        ("Ingen endring", 0),
        ("Moderat vekst", 15),
        ("Normal vekst", 33.3),
        ("Sterk vekst", 50)
    ]
    
    scenario_resultater = []
    
    for scenario_navn, endring_prosent in scenarios:
        scenario_salgspris = boligpris * (1 + endring_prosent / 100)
        scenario_netto = scenario_salgspris - salgskostnader - gjenstaaende_laan
        
        # Bruk samme modell som valgt
        if "Modell 1" in fordelingsmodell:
            scenario_a = scenario_netto * (total_investert_a / total_investert) if total_investert > 0 else scenario_netto * 0.5
            scenario_b = scenario_netto * (total_investert_b / total_investert) if total_investert > 0 else scenario_netto * 0.5
        elif "Modell 2" in fordelingsmodell:
            if scenario_netto > total_investert:
                scenario_gevinst = scenario_netto - total_investert
                ek_andel_a = egenkapital_a / egenkapital if egenkapital > 0 else 0.5
                scenario_a = total_investert_a + (scenario_gevinst * ek_andel_a)
                scenario_b = total_investert_b + (scenario_gevinst * (1 - ek_andel_a))
            else:
                scenario_a = scenario_netto * (total_investert_a / total_investert) if total_investert > 0 else scenario_netto * 0.5
                scenario_b = scenario_netto * (total_investert_b / total_investert) if total_investert > 0 else scenario_netto * 0.5
        elif "Modell 3" in fordelingsmodell:
            if scenario_netto > total_investert:
                scenario_gevinst = scenario_netto - total_investert
                scenario_a = total_investert_a + (scenario_gevinst * 0.5)
                scenario_b = total_investert_b + (scenario_gevinst * 0.5)
            else:
                scenario_a = scenario_netto * (total_investert_a / total_investert) if total_investert > 0 else scenario_netto * 0.5
                scenario_b = scenario_netto * (total_investert_b / total_investert) if total_investert > 0 else scenario_netto * 0.5
        else:  # Hybrid
            if endring_prosent > 0:
                if scenario_netto > total_investert:
                    scenario_gevinst = scenario_netto - total_investert
                    ek_andel_a = egenkapital_a / egenkapital if egenkapital > 0 else 0.5
                    scenario_a = total_investert_a + (scenario_gevinst * ek_andel_a)
                    scenario_b = total_investert_b + (scenario_gevinst * (1 - ek_andel_a))
                else:
                    scenario_a = scenario_netto * (total_investert_a / total_investert) if total_investert > 0 else scenario_netto * 0.5
                    scenario_b = scenario_netto * (total_investert_b / total_investert) if total_investert > 0 else scenario_netto * 0.5
            else:
                scenario_a = scenario_netto * (total_investert_a / total_investert) if total_investert > 0 else scenario_netto * 0.5
                scenario_b = scenario_netto * (total_investert_b / total_investert) if total_investert > 0 else scenario_netto * 0.5
        
        scenario_resultater.append({
            'Scenario': scenario_navn,
            'Verdiendring': f"{endring_prosent:+.0f}%",
            'Salgspris': scenario_salgspris,
            f'{navn_a} gevinst': scenario_a - total_investert_a,
            f'{navn_b} gevinst': scenario_b - total_investert_b
        })
    
    df_scenarios = pd.DataFrame(scenario_resultater)
    
    st.dataframe(
        df_scenarios.style.format({
            'Salgspris': '{:,.0f} kr',
            f'{navn_a} gevinst': lambda x: f"{x:+,.0f} kr",
            f'{navn_b} gevinst': lambda x: f"{x:+,.0f} kr"
        }).background_gradient(subset=[f'{navn_a} gevinst', f'{navn_b} gevinst'],
                               cmap='RdYlGn', vmin=-500000, vmax=1000000),
        use_container_width=True,
        hide_index=True
    )
    
    # Viktig informasjon
    st.markdown("---")
    st.warning("""
    **⚖️ VIKTIG: Juridisk binding**
    
    Denne kalkulatoren gir kun veiledende beregninger. For å gjøre avtalen juridisk bindende:
    
    1. **Samboeravtale**: Regulerer eierskap og fordeling ved brudd
    2. **Ektepakt**: For gifte par, overstyrer ekteskapsloven
    3. **Sameiekontrakt**: Detaljert avtale om boligsameie
    
    **Avtalen bør inneholde:**
    - Eierandeler ved kjøp
    - Fordeling av løpende kostnader
    - Håndtering av verdiendring
    - Prosedyre ved salg
    - Forkjøpsrett
    - Konfliktløsning
    
    💡 **Anbefaling**: Konsulter advokat for å sikre at avtalen er gyldig og dekker deres situasjon.
    """)
with tab8:  # Eller legg i eksisterende tab
    st.header("🎯 Ekstra nedbetaling og ulik betalingsevne")
    
    st.markdown("""
    Når én person har mulighet til å betale ekstra ned på lånet, må dette håndteres rettferdig.
    Ekstra nedbetaling går direkte på hovedstolen og sparer betydelige rentekostnader.
    """)
    
    # Input for ekstra nedbetaling
    st.subheader("💵 Planlagt ekstra nedbetaling")
    
    col1, col2 = st.columns(2)
    
    with col1:
        ekstra_nedbetaling_aar = st.number_input(
            "Hvor mange år fremover?",
            min_value=1,
            max_value=10,
            value=5,
            help="Periode for ekstra nedbetaling",
            key="ekstra_nedbetaling_aar"
        )

        hvem_betaler_ekstra = st.radio(
            "Hvem betaler ekstra?",
            [navn_a, navn_b, "Begge"],
            horizontal=True,
            key="hvem_betaler_ekstra"
        )

    with col2:
        if hvem_betaler_ekstra == "Begge":
            ekstra_per_mnd_a = st.number_input(
                f"Ekstra fra {navn_a} (kr/mnd)",
                min_value=0,
                max_value=50000,
                value=5000,
                step=1000,
                key="ekstra_per_mnd_a_begge"
            )
            ekstra_per_mnd_b = st.number_input(
                f"Ekstra fra {navn_b} (kr/mnd)",
                min_value=0,
                max_value=50000,
                value=3000,
                step=1000,
                key="ekstra_per_mnd_b_begge"
            )
        elif hvem_betaler_ekstra == navn_a:
            ekstra_per_mnd_a = st.number_input(
                f"Ekstra fra {navn_a} (kr/mnd)",
                min_value=0,
                max_value=50000,
                value=10000,
                step=1000,
                key="ekstra_per_mnd_a_solo"
            )
            ekstra_per_mnd_b = 0
        else:
            ekstra_per_mnd_b = st.number_input(
                f"Ekstra fra {navn_b} (kr/mnd)",
                min_value=0,
                max_value=50000,
                value=10000,
                step=1000,
                key="ekstra_per_mnd_b_solo"
            )
            ekstra_per_mnd_a = 0
    
    # Beregn total ekstra nedbetaling
    total_ekstra_a = ekstra_per_mnd_a * 12 * ekstra_nedbetaling_aar
    total_ekstra_b = ekstra_per_mnd_b * 12 * ekstra_nedbetaling_aar
    total_ekstra = total_ekstra_a + total_ekstra_b
    
    # Beregn rentesparing
    gjennomsnittlig_gjenstaaende = laanebelop * 0.6  # Forenklet
    rentesparing = (gjennomsnittlig_gjenstaaende * (rente/100) * ekstra_nedbetaling_aar * 
                   (total_ekstra / laanebelop))
    
    # Vis effekt av ekstra nedbetaling
    st.markdown("### 📊 Effekt av ekstra nedbetaling")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total ekstra nedbetaling", f"{total_ekstra:,.0f} kr")
    with col2:
        st.metric("Estimert rentesparing", f"{rentesparing:,.0f} kr")
    with col3:
        ny_nedbetalingstid = nedbetalingstid * (laanebelop / (laanebelop + total_ekstra))
        st.metric("Ny nedbetalingstid", f"~{ny_nedbetalingstid:.1f} år",
                 delta=f"{nedbetalingstid - ny_nedbetalingstid:.1f} år spart")
    with col4:
        roi = (rentesparing / total_ekstra * 100) if total_ekstra > 0 else 0
        st.metric("Avkastning", f"{roi:.1f}%",
                 help="Rentesparing som % av ekstra nedbetaling")
    
    # HÅNDTERINGSMODELLER
    st.markdown("---")
    st.subheader("⚖️ Håndteringsmodeller for ekstra nedbetaling")
    
    haandtering_modell = st.radio(
        "Velg håndteringsmodell:",
        [
            "Modell A: Økt eierandel (mest vanlig)",
            "Modell B: Lån til partner",
            "Modell C: Reduserte fremtidige betalinger",
            "Modell D: Kombinasjon"
        ]
    )
    
    # Beregn basert på valgt modell
    if "Modell A" in haandtering_modell:
        st.info("""
        **Modell A: Økt eierandel** ✅ MEST VANLIG
        
        Den som betaler ekstra får tilsvarende økt eierandel i boligen.
        
        **Fordeler:**
        - Enkel og rettferdig
        - Direkte kobling mellom betaling og eierskap
        - Ingen gjeld mellom partnere
        
        **Ulemper:**
        - Kan gi skjev eierfordeling over tid
        - Krever nøye bokføring
        """)
        
        # Beregn ny eierandel
        # Original eierandel (fra egenkapital + normal nedbetaling)
        normal_nedbetaling_a = (laanebelop / nedbetalingstid) * ekstra_nedbetaling_aar * 0.5
        normal_nedbetaling_b = (laanebelop / nedbetalingstid) * ekstra_nedbetaling_aar * 0.5
        
        if fordeling_type == "Proporsjonal etter inntekt":
            andel = kostnad_a / (kostnad_a + kostnad_b) if (kostnad_a + kostnad_b) > 0 else 0.5
            normal_nedbetaling_a *= andel / 0.5
            normal_nedbetaling_b *= (1-andel) / 0.5
        
        # Total investering inkludert ekstra
        total_investert_inkl_ekstra_a = egenkapital_a + normal_nedbetaling_a + total_ekstra_a
        total_investert_inkl_ekstra_b = egenkapital_b + normal_nedbetaling_b + total_ekstra_b
        total_investert_inkl_ekstra = total_investert_inkl_ekstra_a + total_investert_inkl_ekstra_b
        
        # Ny eierandel
        ny_eierandel_a = (total_investert_inkl_ekstra_a / boligpris) * 100
        ny_eierandel_b = (total_investert_inkl_ekstra_b / boligpris) * 100
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"**{navn_a}**")
            st.metric("Original eierandel", f"{(egenkapital_a/boligpris)*100:.1f}%")
            st.metric("Ny eierandel", f"{ny_eierandel_a:.1f}%",
                     delta=f"+{ny_eierandel_a - (egenkapital_a/boligpris)*100:.1f}%")
            st.caption(f"Ekstra investert: {total_ekstra_a:,.0f} kr")
        
        with col2:
            st.markdown(f"**{navn_b}**")
            st.metric("Original eierandel", f"{(egenkapital_b/boligpris)*100:.1f}%")
            st.metric("Ny eierandel", f"{ny_eierandel_b:.1f}%",
                     delta=f"+{ny_eierandel_b - (egenkapital_b/boligpris)*100:.1f}%")
            st.caption(f"Ekstra investert: {total_ekstra_b:,.0f} kr")
    
    elif "Modell B" in haandtering_modell:
        st.info("""
        **Modell B: Lån til partner** 💰
        
        Den som betaler ekstra gir et lån til partneren for deres "andel" av ekstrabetalingen.
        
        **Fordeler:**
        - Bevarer avtalt eierfordeling
        - Partner får fordel av rentesparing
        - Kan tilbakebetales over tid
        
        **Ulemper:**
        - Skaper gjeldsforhold mellom partnere
        - Krever låneavtale og renter
        - Kan komplisere forholdet
        """)
        
        # Beregn lån mellom partnere
        if hvem_betaler_ekstra == navn_a:
            laan_til_b = total_ekstra * 0.5  # B's "andel" av ekstrabetalingen
            st.metric(f"Lån fra {navn_a} til {navn_b}", f"{laan_til_b:,.0f} kr")
            
            # Vis tilbakebetalingsplan
            intern_rente = st.slider("Intern rente på lånet (%)", 0.0, 5.0, 2.0, 0.5, key="intern_rente_a")
            tilbakebetalingstid = st.slider("Tilbakebetalingstid (år)", 1, 10, 5, key="tilbakebetalingstid_a")

            maanedlig_betaling = beregn_terminbelop(laan_til_b, intern_rente, tilbakebetalingstid)
            st.metric(f"Månedlig tilbakebetaling fra {navn_b}", f"{maanedlig_betaling:,.0f} kr")

        elif hvem_betaler_ekstra == navn_b:
            laan_til_a = total_ekstra * 0.5
            st.metric(f"Lån fra {navn_b} til {navn_a}", f"{laan_til_a:,.0f} kr")

            intern_rente = st.slider("Intern rente på lånet (%)", 0.0, 5.0, 2.0, 0.5, key="intern_rente_b")
            tilbakebetalingstid = st.slider("Tilbakebetalingstid (år)", 1, 10, 5, key="tilbakebetalingstid_b")
            
            maanedlig_betaling = beregn_terminbelop(laan_til_a, intern_rente, tilbakebetalingstid)
            st.metric(f"Månedlig tilbakebetaling fra {navn_a}", f"{maanedlig_betaling:,.0f} kr")
    
    elif "Modell C" in haandtering_modell:
        st.info("""
        **Modell C: Reduserte fremtidige betalinger** 📉
        
        Den som betaler ekstra får redusert sin andel av fremtidige terminbeløp.
        
        **Fordeler:**
        - Utjevner betalingsevne over tid
        - Ingen endring i eierskap
        - Fleksibel løsning
        
        **Ulemper:**
        - Kompleks å beregne nøyaktig
        - Krever løpende justering
        - Kan bli uoversiktlig
        """)
        
        # Beregn kreditt for fremtidige betalinger
        if total_ekstra > 0:
            # Den som har betalt ekstra får "kreditt"
            kreditt_a = total_ekstra_a
            kreditt_b = total_ekstra_b
            
            # Hvor lenge varer kreditten?
            maanedlig_kreditt = terminbelop * 0.5  # Halvparten av terminbeløp
            
            if kreditt_a > 0:
                mnd_med_kreditt_a = kreditt_a / maanedlig_kreditt
                st.metric(f"{navn_a} betaler halv termin i", f"{mnd_med_kreditt_a:.0f} mnd",
                         help=f"Kreditt: {kreditt_a:,.0f} kr")
            
            if kreditt_b > 0:
                mnd_med_kreditt_b = kreditt_b / maanedlig_kreditt
                st.metric(f"{navn_b} betaler halv termin i", f"{mnd_med_kreditt_b:.0f} mnd",
                         help=f"Kreditt: {kreditt_b:,.0f} kr")
            
            # Vis ny betalingsfordeling
            st.markdown("**Justert månedlig betaling:**")
            
            if kreditt_a > 0 and kreditt_b == 0:
                ny_betaling_a = kostnad_a - (kreditt_a / (mnd_med_kreditt_a))
                ny_betaling_b = kostnad_b + (kreditt_a / (mnd_med_kreditt_a))
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(f"{navn_a} (med kreditt)", f"{ny_betaling_a:,.0f} kr/mnd",
                             delta=f"{ny_betaling_a - kostnad_a:,.0f} kr")
                with col2:
                    st.metric(f"{navn_b} (kompenserer)", f"{ny_betaling_b:,.0f} kr/mnd",
                             delta=f"{ny_betaling_b - kostnad_b:,.0f} kr")
    
    else:  # Modell D: Kombinasjon
        st.info("""
        **Modell D: Kombinasjon** 🔄
        
        Kombinerer elementer fra de andre modellene.
        
        **Eksempel:**
        - 50% går til økt eierandel
        - 25% som kreditt for fremtidige betalinger
        - 25% som rentefri "gave" til felles beste
        
        **Fordeler:**
        - Fleksibel og tilpassbar
        - Kan balansere ulike hensyn
        - Tar høyde for relasjonsdynamikk
        
        **Ulemper:**
        - Mest kompleks å administrere
        - Krever detaljert avtale
        """)
        
        # La bruker definere fordeling
        st.markdown("**Definer fordeling av ekstra nedbetaling:**")

        andel_eierskap = st.slider("% til økt eierandel", 0, 100, 50, 10, key="andel_eierskap")
        andel_kreditt = st.slider("% til kreditt for fremtidige betalinger", 0, 100, 25, 10, key="andel_kreditt")
        andel_gave = 100 - andel_eierskap - andel_kreditt
        
        st.info(f"Resterende {andel_gave}% regnes som bidrag til felles beste")
        
        # Beregn effekt
        if total_ekstra > 0:
            ekstra_til_eierskap = total_ekstra * (andel_eierskap / 100)
            ekstra_til_kreditt = total_ekstra * (andel_kreditt / 100)
            ekstra_til_felles = total_ekstra * (andel_gave / 100)
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Til økt eierandel", f"{ekstra_til_eierskap:,.0f} kr")
            with col2:
                st.metric("Til kreditt", f"{ekstra_til_kreditt:,.0f} kr")
            with col3:
                st.metric("Til felles", f"{ekstra_til_felles:,.0f} kr")
    
    # Sammenligning av modeller
    st.markdown("---")
    st.subheader("📊 Sammenligning ved salg")
    
    st.markdown("Hvordan påvirker valg av modell utfallet ved salg etter 10 år?")
    
    # Anta salg etter 10 år med 30% verdistigning
    salgsaar_eks = 10
    salgspris_eks = boligpris * 1.3
    gjenstaaende_eks = laanebelop * 0.6  # Forenklet
    netto_salg_eks = salgspris_eks - gjenstaaende_eks - (salgspris_eks * DOKUMENTAVGIFT_PROSENT)
    
    # Beregn utfall for hver modell
    modeller_sammenligning = []
    
    # Modell A: Økt eierandel
    eierandel_med_ekstra_a = (egenkapital_a + total_ekstra_a) / (egenkapital + total_ekstra) if (egenkapital + total_ekstra) > 0 else 0.5
    eierandel_med_ekstra_b = (egenkapital_b + total_ekstra_b) / (egenkapital + total_ekstra) if (egenkapital + total_ekstra) > 0 else 0.5
    
    utbetaling_modell_a_person_a = netto_salg_eks * eierandel_med_ekstra_a
    utbetaling_modell_a_person_b = netto_salg_eks * eierandel_med_ekstra_b
    
    modeller_sammenligning.append({
        'Modell': 'A: Økt eierandel',
        f'{navn_a}': utbetaling_modell_a_person_a,
        f'{navn_b}': utbetaling_modell_a_person_b,
        'Forskjell': abs(utbetaling_modell_a_person_a - utbetaling_modell_a_person_b)
    })
    
    # Modell B: Lån (eierandel uendret, men gjeld mellom partnere)
    utbetaling_modell_b_person_a = netto_salg_eks * 0.5
    utbetaling_modell_b_person_b = netto_salg_eks * 0.5
    
    modeller_sammenligning.append({
        'Modell': 'B: Lån mellom partnere',
        f'{navn_a}': utbetaling_modell_b_person_a,
        f'{navn_b}': utbetaling_modell_b_person_b,
        'Forskjell': 0
    })
    
    # Modell C: Kreditt (samme som B ved salg)
    modeller_sammenligning.append({
        'Modell': 'C: Kreditt',
        f'{navn_a}': utbetaling_modell_b_person_a,
        f'{navn_b}': utbetaling_modell_b_person_b,
        'Forskjell': 0
    })
    
    df_modell_sammenligning = pd.DataFrame(modeller_sammenligning)
    
    st.dataframe(
        df_modell_sammenligning.style.format({
            f'{navn_a}': '{:,.0f} kr',
            f'{navn_b}': '{:,.0f} kr',
            'Forskjell': '{:,.0f} kr'
        }),
        use_container_width=True,
        hide_index=True
    )
    
    # Anbefalinger
    st.markdown("---")
    st.subheader("💡 Anbefalinger")
    
    st.success("""
    **Beste praksis for ekstra nedbetaling:**
    
    1. **Modell A (Økt eierandel)** er vanligst og enklest
       - Brukes av ~70% av samboere/ektepar
       - Rettferdig og transparent
       - Krever kun god bokføring
    
    2. **Dokumenter alt**
       - Før kvitteringer for alle ekstra innbetalinger
       - Spesifiser hvem som betalte hva
       - Oppdater samboeravtale ved store endringer
    
    3. **Vurder skattefordeler**
       - Ekstra nedbetaling reduserer rentefradrag
       - Kan være bedre å investere i fond hvis lav rente
       - Konsulter gjerne økonomiradgiver
    
    4. **Kommuniser åpent**
       - Diskuter før noen gjør ekstra nedbetaling
       - Bli enige om modell på forhånd
       - Revurder ved endrede forhold
    """)
    
    st.info("""
    📌 **Husk**: Uansett modell - det viktigste er at begge parter forstår og er enige om håndteringen 
    FØR ekstra nedbetaling gjøres. Transparens og kommunikasjon er nøkkelen til å unngå konflikter.
    """)
# Sidebar for scenario-håndtering
with st.sidebar:
    st.header("💾 Lagring og lasting")
    
    # Seksjon for å lagre nåværende scenario
    st.subheader("Lagre scenario")
    
    scenario_navn_lagring = st.text_input(
        "Scenario navn",
        value=f"Bolig_{datetime.now().strftime('%Y%m%d')}",
        key="scenario_navn_save"
    )
    
    if st.button("💾 Last ned scenario", type="primary"):
        # Samle all data i en dictionary
        scenario_data = {
            'navn': scenario_navn_lagring,
            'versjon': '2.0',
            'boligdata': {
                'boligpris': boligpris,
                'egenkapital': egenkapital,
                'egenkapital_a': egenkapital_a if 'egenkapital_a' in locals() else egenkapital/2,
                'egenkapital_b': egenkapital_b if 'egenkapital_b' in locals() else egenkapital/2,
                'rente': rente,
                'nedbetalingstid': nedbetalingstid,
                'felleskostnader': felleskostnader,
                'laanebelop': laanebelop
            },
            'personer': {
                'navn_a': navn_a,
                'navn_b': navn_b,
                'brutto_aar_a': brutto_aar_a,
                'brutto_aar_b': brutto_aar_b,
                'jobtype_a': jobtype_a if 'jobtype_a' in locals() else 'Fast ansatt',
                'jobtype_b': jobtype_b if 'jobtype_b' in locals() else 'Fast ansatt'
            },
            'fordeling': {
                'fordeling_type': fordeling_type,
                'custom_split': custom_split if 'custom_split' in locals() else None
            },
            'barekraftighet': {
                'studielaan_a': st.session_state.get('studielaan_a', 0),
                'studielaan_b': st.session_state.get('studielaan_b', 0),
                'billaan_a': st.session_state.get('billaan_a', 0),
                'billaan_b': st.session_state.get('billaan_b', 0),
                'mat_a': st.session_state.get('mat_a', 4000),
                'mat_b': st.session_state.get('mat_b', 3500),
                'transport_a': st.session_state.get('transport_a', 1500),
                'transport_b': st.session_state.get('transport_b', 2000),
                'diverse_a': st.session_state.get('diverse_a', 3000),
                'diverse_b': st.session_state.get('diverse_b', 2500)
            },
            'beregninger': {
                'terminbelop': terminbelop,
                'total_mnd_kostnad': total_mnd_kostnad,
                'kostnad_a': kostnad_a,
                'kostnad_b': kostnad_b,
                'belastning_a': belastning_a if 'belastning_a' in locals() else 0,
                'belastning_b': belastning_b if 'belastning_b' in locals() else 0
            }
        }
        
        # Konverter til JSON
        json_str = lagre_scenario_til_fil(scenario_data)
        
        # Last ned knapp
        st.download_button(
            label="📥 Last ned JSON fil",
            data=json_str,
            file_name=f"{scenario_navn_lagring}.json",
            mime="application/json"
        )
        
        st.success("✅ Scenario klar for nedlasting!")
    
    st.markdown("---")
    # Seksjon for å laste opp scenario
    st.subheader("Last inn scenario")
    
    uploaded_file = st.file_uploader(
        "Velg en scenario-fil",
        type=['json'],
        help="Last opp en tidligere lagret scenario JSON-fil"
    )
    
    if uploaded_file is not None:
        if st.button("📤 Last inn scenario"):
            scenario_data = last_scenario_fra_fil(uploaded_file)
            
            if scenario_data:
                # Lagre i session state for å kunne oppdatere verdiene
                st.session_state.loaded_scenario = scenario_data
                st.success(f"✅ Lastet scenario: {scenario_data.get('navn', 'Ukjent')}")
                st.info("Klikk 'Bruk scenario' for å fylle inn verdiene")
    
    # Knapp for å bruke lastet scenario
    if 'loaded_scenario' in st.session_state:
        if st.button("✨ Bruk scenario", type="primary"):
            # Her må vi oppdatere session state med verdiene
            # Dette krever at vi bruker st.session_state for alle inputs
            scenario = st.session_state.loaded_scenario
            
            # Oppdater session state med scenario-verdier
            for key, value in scenario.get('barekraftighet', {}).items():
                st.session_state[key] = value
            
            st.success("✅ Scenario aktivert! Refresh siden for å se endringene.")
            st.balloons()
    
    st.markdown("---")
    
    # Sammenlign scenarioer
    st.subheader("📊 Sammenlign scenarioer")
    
    # Tillat opplasting av flere filer for sammenligning
    files_to_compare = st.file_uploader(
        "Velg scenarioer å sammenligne",
        type=['json'],
        accept_multiple_files=True,
        key="compare_files"
    )
    
    if len(files_to_compare) >= 2:
        if st.button("🔍 Sammenlign"):
            comparison_data = []
            
            for file in files_to_compare:
                scenario = last_scenario_fra_fil(file)
                if scenario:
                    comparison_data.append({
                        'Scenario': scenario.get('navn', 'Ukjent'),
                        'Boligpris': scenario['boligdata']['boligpris'],
                        'Lånebeløp': scenario['boligdata']['laanebelop'],
                        'Rente': scenario['boligdata']['rente'],
                        'Månedlig': scenario['beregninger']['total_mnd_kostnad'],
                        f"Belastning {scenario['personer']['navn_a']}": 
                            scenario['beregninger'].get('belastning_a', 0),
                        f"Belastning {scenario['personer']['navn_b']}": 
                            scenario['beregninger'].get('belastning_b', 0)
                    })
            
            if comparison_data:
                df_comparison = pd.DataFrame(comparison_data)
                st.dataframe(
                    df_comparison.style.format({
                        'Boligpris': '{:,.0f} kr',
                        'Lånebeløp': '{:,.0f} kr',
                        'Rente': '{:.1f}%',
                        'Månedlig': '{:,.0f} kr'
                    }).background_gradient(subset=['Månedlig'], cmap='RdYlGn_r'),
                    use_container_width=True
                )
    
    st.markdown("---")
    
    # Quick save/load med session state
    st.subheader("⚡ Rask-lagring")
    
    # Maks 5 quick saves
    if 'quick_saves' not in st.session_state:
        st.session_state.quick_saves = []
    
    save_name = st.text_input("Navn på rask-lagring", key="quick_save_name")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("💾 Rask-lagre"):
            if save_name:
                quick_save = {
                    'navn': save_name,
                    'tid': datetime.now().strftime('%H:%M:%S'),
                    'boligpris': boligpris,
                    'rente': rente,
                    'kostnad': total_mnd_kostnad if 'total_mnd_kostnad' in locals() else 0
                }
                
                # Hold maks 5 saves
                st.session_state.quick_saves.append(quick_save)
                if len(st.session_state.quick_saves) > 5:
                    st.session_state.quick_saves.pop(0)
                
                st.success(f"✅ Lagret '{save_name}'")
    
    with col2:
        if st.button("🗑️ Tøm alle"):
            st.session_state.quick_saves = []
            st.info("Alle rask-lagringer slettet")
    
    # Vis quick saves
    if st.session_state.quick_saves:
        st.markdown("**Lagrede scenarioer:**")
        for save in st.session_state.quick_saves:
            st.caption(
                f"📌 {save['navn']} ({save['tid']}) - "
                f"{save['boligpris']:,.0f} kr @ {save['rente']}% = "
                f"{save['kostnad']:,.0f} kr/mnd"
            )
    
    # Info om lagring
    with st.expander("ℹ️ Om lagring"):
        st.markdown("""
        **Lagringsalternativer:**
        
        1. **Last ned JSON** 
           - Permanent lagring på din PC
           - Kan deles med partner
           - Inneholder alle detaljer
        
        2. **Rask-lagring**
           - Midlertidig i nettleseren
           - Forsvinner ved refresh
           - Maks 5 scenarioer
        
        3. **Sammenligning**
           - Last opp flere JSON-filer
           - Se alle scenarioer side ved side
           - Identifiser beste alternativ
        
        **Tips:**
        - Lagre et scenario for hver bolig dere vurderer
        - Bruk beskrivende navn (f.eks. "Grünerløkka_3rom")
        - Del JSON-filer med partner for felles planlegging
        """)
    
st.markdown("---")
st.caption("🏠 Boliglånskalkulator | Alle beregninger er estimater - kontakt bank for nøyaktige tall")
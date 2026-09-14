document.addEventListener("DOMContentLoaded", () => {
    const phoneInput = document.getElementById("phoneInput");
    const searchBtn = document.getElementById("searchBtn");
    const refreshCheck = document.getElementById("refreshCheck");
    const emptyState = document.getElementById("emptyState");
    const loadingState = document.getElementById("loadingState");
    const resultsSection = document.getElementById("resultsSection");
    const reportModal = document.getElementById("reportModal");
    const openReportBtn = document.getElementById("openReportBtn");
    const closeReportBtn = document.getElementById("closeReportBtn");
    const reportForm = document.getElementById("reportForm");
    const historyList = document.getElementById("historyList");

    let currentAnalyzedNumber = "";

    // Load search history on startup
    loadSearchHistory();

    // Attach sample pill clicks
    document.querySelectorAll(".sample-pill").forEach(pill => {
        pill.addEventListener("click", () => {
            const num = pill.getAttribute("data-number");
            phoneInput.value = num;
            performLookup(num, false);
        });
    });

    // Enter key submits search
    phoneInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            performLookup(phoneInput.value, refreshCheck.checked);
        }
    });

    searchBtn.addEventListener("click", () => {
        performLookup(phoneInput.value, refreshCheck.checked);
    });

    // Lookup function
    async function performLookup(numberStr, refresh = false) {
        const clean = (numberStr || "").trim();
        if (!clean) {
            phoneInput.focus();
            return;
        }

        currentAnalyzedNumber = clean;
        emptyState.classList.add("hidden");
        resultsSection.classList.add("hidden");
        loadingState.classList.remove("hidden");
        searchBtn.disabled = true;

        try {
            const url = `/api/v1/lookup?number=${encodeURIComponent(clean)}&refresh=${refresh ? "true" : "false"}`;
            const res = await fetch(url);
            if (!res.ok) {
                const errData = await res.json().catch(() => ({ detail: "Erro na pesquisa" }));
                throw new Error(errData.detail || "Falha na comunicação com o servidor.");
            }
            const data = await res.json();
            renderResults(data);
            loadSearchHistory(); // Refresh history
        } catch (err) {
            alert(`Erro ao analisar o número: ${err.message}`);
            emptyState.classList.remove("hidden");
        } finally {
            loadingState.classList.add("hidden");
            searchBtn.disabled = false;
        }
    }

    // Render results into UI
    function renderResults(data) {
        resultsSection.classList.remove("hidden");
        const norm = data.normalized;
        const anacom = data.anacom;
        const risk = data.risk_score;
        const level = data.risk_level;

        // Formatted number and badge
        document.getElementById("resNationalNumber").textContent = norm.national_format || norm.raw_input;
        document.getElementById("resE164Number").textContent = norm.e164;
        document.getElementById("resCountry").textContent = `${norm.country_name} (${norm.region_code || "PT"})`;
        document.getElementById("resDuration").textContent = `${data.query_duration_ms} ms`;
        
        const cacheIndicator = document.getElementById("resCacheStatus");
        if (data.cached) {
            cacheIndicator.textContent = "Cache Local (24h)";
            cacheIndicator.className = "text-xs font-mono px-2 py-0.5 rounded bg-blue-900/60 text-blue-300 border border-blue-700/50";
        } else {
            cacheIndicator.textContent = "Live Scan";
            cacheIndicator.className = "text-xs font-mono px-2 py-0.5 rounded bg-emerald-900/60 text-emerald-300 border border-emerald-700/50";
        }

        // Risk Meter & Level
        const riskMeterFill = document.getElementById("riskMeterFill");
        const riskScoreText = document.getElementById("riskScoreText");
        const riskLevelBadge = document.getElementById("riskLevelBadge");
        const callerCatBadge = document.getElementById("callerCategoryBadge");

        riskScoreText.textContent = risk;
        riskMeterFill.style.width = `${risk}%`;

        // Confidence & Matched By Badges
        const confBadge = document.getElementById("resConfidenceBadge");
        const matchBadge = document.getElementById("resMatchedByBadge");
        const conf = data.confidence || "LOW";
        const matchedBy = data.matched_by || "anacom_range";

        if (conf === "HIGH") {
            confBadge.className = "px-3 py-1 rounded-xl text-xs font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40";
            confBadge.textContent = "Confiança: ALTA";
        } else if (conf === "MEDIUM") {
            confBadge.className = "px-3 py-1 rounded-xl text-xs font-semibold bg-blue-500/20 text-blue-300 border border-blue-500/40";
            confBadge.textContent = "Confiança: MÉDIA";
        } else {
            confBadge.className = "px-3 py-1 rounded-xl text-xs font-semibold bg-slate-800 text-slate-400 border border-slate-700";
            confBadge.textContent = "Confiança: BAIXA";
        }

        const matchLabels = {
            "trusted_directory_exact": "Diretório Oficial Exato",
            "dork_consensus": "Consenso OSINT Multi-Fonte",
            "geographic_prefix_inference": "Inferência de Bloco Institucional",
            "dork_inference": "Pesquisa OSINT Dorking",
            "crowdsourced_only": "Crowdsourcing Comunitário",
            "anacom_range": "Gama Regulada ANACOM",
        };
        matchBadge.textContent = matchLabels[matchedBy] || matchedBy;

        callerCatBadge.textContent = data.caller_category;

        if (level === "CRITICAL") {
            riskMeterFill.className = "risk-meter-fill bg-rose-500 shadow-lg shadow-rose-500/50";
            riskLevelBadge.className = "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-rose-500/20 text-rose-400 border border-rose-500/40";
            riskLevelBadge.textContent = "CRÍTICO / PERIGO";
        } else if (level === "HIGH") {
            riskMeterFill.className = "risk-meter-fill bg-amber-500 shadow-lg shadow-amber-500/50";
            riskLevelBadge.className = "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-amber-500/20 text-amber-400 border border-amber-500/40";
            riskLevelBadge.textContent = "ALTO RISCO";
        } else if (level === "MEDIUM") {
            riskMeterFill.className = "risk-meter-fill bg-yellow-500 shadow-lg shadow-yellow-500/50";
            riskLevelBadge.className = "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-yellow-500/20 text-yellow-400 border border-yellow-500/40";
            riskLevelBadge.textContent = "MODERADO";
        } else {
            riskMeterFill.className = "risk-meter-fill bg-emerald-500 shadow-lg shadow-emerald-500/50";
            riskLevelBadge.className = "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-400 border border-emerald-500/40";
            riskLevelBadge.textContent = "CONFIÁVEL / BAIXO";
        }

        // Recommendations
        document.getElementById("recPtText").textContent = data.recommendation;
        document.getElementById("recEnText").textContent = data.recommendation_en;

        // Operator & Network Metadata Card
        const opMeta = data.operator_metadata;
        document.getElementById("carrierName").textContent = opMeta.assigned_carrier || "Não identificado";
        document.getElementById("lineType").textContent = norm.line_type || "UNKNOWN";
        document.getElementById("technologyText").textContent = opMeta.technology || "PSTN / Celular";
        document.getElementById("geoAreaText").textContent = opMeta.geographic_area || norm.country_name;

        const voipBadge = document.getElementById("voipBadge");
        if (opMeta.is_voip_nomadic) {
            voipBadge.classList.remove("hidden");
            voipBadge.textContent = "VoIP / Nómada (30x)";
        } else {
            voipBadge.classList.add("hidden");
        }

        // ANACOM Section
        const anacomBox = document.getElementById("anacomBox");
        if (anacom && anacom.matched_prefix) {
            anacomBox.classList.remove("hidden");
            document.getElementById("anacomPrefix").textContent = `Prefixo PNN: ${anacom.matched_prefix}`;
            document.getElementById("anacomService").textContent = anacom.designation || anacom.service_type;
            document.getElementById("anacomOperators").textContent = anacom.primary_operators.join(", ");
            document.getElementById("anacomNotes").textContent = anacom.notes || "Alocação regulada pela ANACOM.";
        } else {
            anacomBox.classList.add("hidden");
        }

        // Crowdsourced Intelligence Card
        const crowd = data.crowdsourced_reports || {};
        document.getElementById("totalSearches").textContent = (crowd.total_searches || 0).toLocaleString();
        document.getElementById("totalReports").textContent = (crowd.total_reports || 0).toLocaleString();

        const tagsContainer = document.getElementById("tagsContainer");
        tagsContainer.innerHTML = "";
        const tags = crowd.tags || [];
        if (tags.length === 0) {
            tagsContainer.innerHTML = `<span class="text-xs text-slate-500 italic">Nenhuma etiqueta reportada ainda.</span>`;
        } else {
            tags.forEach(t => {
                const badge = document.createElement("span");
                badge.className = "text-xs px-2.5 py-1 rounded-md bg-slate-800 text-slate-300 border border-slate-700 font-medium";
                badge.textContent = `# ${t}`;
                tagsContainer.appendChild(badge);
            });
        }

        // Commercial Entity Card
        const bizSection = document.getElementById("commercialEntitySection");
        const biz = data.commercial_entity;
        if (biz && biz.is_commercial_entity) {
            bizSection.classList.remove("hidden");
            document.getElementById("bizName").textContent = biz.entity_name || "Entidade Empresarial Identificada";
            document.getElementById("bizCategory").textContent = biz.category || "Empresa / Registo Comercial";
            const bizLink = document.getElementById("bizWebsite");
            if (biz.website) {
                bizLink.href = biz.website.startsWith("http") ? biz.website : `https://${biz.website}`;
                bizLink.textContent = biz.website;
                bizLink.classList.remove("hidden");
            } else {
                bizLink.classList.add("hidden");
            }

            const snippetBox = document.getElementById("bizSnippets");
            snippetBox.innerHTML = "";
            (biz.evidence_snippets || []).forEach(snip => {
                const p = document.createElement("p");
                p.className = "text-xs text-slate-400 bg-slate-900/60 p-2 rounded border border-slate-800";
                p.textContent = snip;
                snippetBox.appendChild(p);
            });
        } else {
            bizSection.classList.add("hidden");
        }

        // Sources Status Breakdown
        const sourcesList = document.getElementById("sourcesList");
        sourcesList.innerHTML = "";
        (data.sources || []).forEach(src => {
            const div = document.createElement("div");
            div.className = "flex items-center justify-between text-xs py-1.5 border-b border-slate-800/80 last:border-0";
            const statusColor = src.success ? "text-emerald-400" : "text-slate-500";
            const statusText = src.success ? (src.spam_score !== null ? `Score: ${src.spam_score}/10` : "OK") : (src.error_message ? "Indisponível" : "Sem registo");
            div.innerHTML = `
                <span class="text-slate-300 font-medium">${src.source_name}</span>
                <span class="${statusColor} font-mono">${statusText}</span>
            `;
            sourcesList.appendChild(div);
        });

        // Comments Feed
        const commentsList = document.getElementById("commentsList");
        commentsList.innerHTML = "";
        const comments = crowd.recent_comments || [];
        if (comments.length === 0) {
            commentsList.innerHTML = `
                <div class="text-center py-6 text-slate-500 text-sm">
                    Ainda não existem comentários ou queixas registadas para este número. Seja o primeiro a reportar!
                </div>
            `;
        } else {
            comments.forEach(c => {
                const cDiv = document.createElement("div");
                cDiv.className = "p-3.5 rounded-lg bg-slate-900/70 border border-slate-800 text-sm space-y-1";
                cDiv.innerHTML = `
                    <div class="flex items-center justify-between text-xs text-slate-400">
                        <span class="font-semibold text-slate-300">${escapeHtml(c.author || "Anónimo")}</span>
                        <div class="flex items-center gap-2">
                            ${c.tag ? `<span class="px-2 py-0.5 rounded bg-rose-950/70 text-rose-300 border border-rose-800/50">${escapeHtml(c.tag)}</span>` : ""}
                            <span class="font-mono text-[11px]">${escapeHtml(c.source)}</span>
                        </div>
                    </div>
                    <p class="text-slate-300 leading-relaxed text-xs sm:text-sm pt-1">${escapeHtml(c.text)}</p>
                `;
                commentsList.appendChild(cDiv);
            });
        }
    }

    // Load recent lookups history
    async function loadSearchHistory() {
        try {
            const res = await fetch("/api/v1/history?limit=8");
            if (!res.ok) return;
            const items = await res.json();
            historyList.innerHTML = "";

            if (items.length === 0) {
                historyList.innerHTML = `<li class="text-xs text-slate-500 italic p-2">Sem histórico recente</li>`;
                return;
            }

            items.forEach(item => {
                const li = document.createElement("li");
                li.className = "flex items-center justify-between p-2 rounded-lg hover:bg-slate-800/60 cursor-pointer text-xs transition border border-transparent hover:border-slate-700";
                
                let badgeClass = "text-emerald-400 bg-emerald-950/50";
                if (item.risk_level === "CRITICAL") badgeClass = "text-rose-400 bg-rose-950/50";
                else if (item.risk_level === "HIGH") badgeClass = "text-amber-400 bg-amber-950/50";
                else if (item.risk_level === "MEDIUM") badgeClass = "text-yellow-400 bg-yellow-950/50";

                li.innerHTML = `
                    <div class="flex items-center gap-2">
                        <span class="font-mono font-medium text-slate-200">${item.national_format || item.phone_e164}</span>
                        <span class="text-[10px] px-1.5 py-0.5 rounded ${badgeClass}">${item.risk_level}</span>
                    </div>
                    <span class="text-slate-500 text-[11px]">${item.caller_category.split("/")[0]}</span>
                `;
                li.addEventListener("click", () => {
                    phoneInput.value = item.national_format || item.phone_e164;
                    performLookup(phoneInput.value, false);
                });
                historyList.appendChild(li);
            });
        } catch (e) {
            console.debug("Error loading history:", e);
        }
    }

    // Modal Handlers
    const openTrustBtn = document.getElementById("openTrustBtn");
    if (openTrustBtn) {
        openTrustBtn.addEventListener("click", () => {
            const num = currentAnalyzedNumber || phoneInput.value;
            document.getElementById("reportPhoneInput").value = num;
            document.getElementById("reportCategory").value = "Contacto Pessoal / Seguro";
            document.getElementById("reportRating").value = "1";
            document.getElementById("reportComment").value = "Contacto pessoal de confiança / empresa legítima.";
            reportModal.classList.remove("hidden");
        });
    }

    openReportBtn.addEventListener("click", () => {
        document.getElementById("reportPhoneInput").value = currentAnalyzedNumber || phoneInput.value;
        document.getElementById("reportCategory").value = "Burla / MBWay";
        document.getElementById("reportRating").value = "10";
        document.getElementById("reportComment").value = "";
        reportModal.classList.remove("hidden");
    });

    closeReportBtn.addEventListener("click", () => {
        reportModal.classList.add("hidden");
    });

    reportModal.addEventListener("click", (e) => {
        if (e.target === reportModal) {
            reportModal.classList.add("hidden");
        }
    });

    // Form submission
    reportForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const payload = {
            phone_number: document.getElementById("reportPhoneInput").value.trim(),
            category: document.getElementById("reportCategory").value,
            caller_name: document.getElementById("reportCallerName").value.trim() || null,
            risk_rating: parseInt(document.getElementById("reportRating").value, 10),
            comment: document.getElementById("reportComment").value.trim(),
        };

        if (!payload.phone_number || !payload.comment) {
            alert("Preencha o número e o comentário.");
            return;
        }

        try {
            const res = await fetch("/api/v1/report", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Falha ao submeter reporte.");
            }
            alert("O seu reporte foi registado com sucesso e a inteligência foi atualizada!");
            reportModal.classList.add("hidden");
            reportForm.reset();
            // Trigger fresh lookup to show the updated risk score and comment
            performLookup(payload.phone_number, true);
        } catch (err) {
            alert(`Erro: ${err.message}`);
        }
    });

    function escapeHtml(str) {
        if (!str) return "";
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
});

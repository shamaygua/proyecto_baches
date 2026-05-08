import { initializeApp } from "https://www.gstatic.com/firebasejs/12.11.0/firebase-app.js";
import { getFirestore, collection, getDocs } from "https://www.gstatic.com/firebasejs/12.11.0/firebase-firestore.js";

const firebaseConfig = {
    apiKey: "AIzaSyCtSrFsAfMsTD4Hu3QV72ELjJVFzCf1WF0",
    authDomain: "proyecto-baches-14183.firebaseapp.com",
    projectId: "proyecto-baches-14183",
    storageBucket: "proyecto-baches-14183.firebasestorage.app",
    messagingSenderId: "530381723314",
    appId: "1:530381723314:web:d8a9192ea512a0e8721bab"
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);

const COCHABAMBA = [-17.3935, -66.1570];
const map = L.map("map").setView(COCHABAMBA, 15);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap",
    maxZoom: 19
}).addTo(map);

let todosLosBaches = [];
let bachesGlobal = [];
let modoVisualizacion = "marcadores";
let marcadorUsuario = null;

let clusterGroup = L.markerClusterGroup();
let heatLayer = null;

const iconoUsuario = L.icon({
    iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
    shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41]
});

function obtenerColor(severidad) {
    if (!severidad) return "gray";
    if (severidad === "alta") return "red";
    if (severidad === "media") return "orange";
    if (severidad === "baja") return "green";
    return "blue";
}

function pesoSeveridad(severidad) {
    if (severidad === "alta") return 1.0;
    if (severidad === "media") return 0.7;
    if (severidad === "baja") return 0.4;
    return 0.3;
}

function nombreTipoDeteccion(tipo) {
    const nombres = {
        bache_confirmado_multimodal: "Confirmado multimodal",
        bache_probable_con_apoyo_visual: "Sensorial con apoyo visual",
        bache_probable_sensorial: "Solo sensorial",
        bache_probable_visual: "Solo visual"
    };

    return nombres[tipo] ?? tipo ?? "no disponible";
}

function formatearFecha(fechaFirestore) {
    if (!fechaFirestore) return "no disponible";

    try {
        let fecha;

        if (typeof fechaFirestore.toDate === "function") {
            fecha = fechaFirestore.toDate();
        } else {
            fecha = new Date(fechaFirestore);
        }

        return fecha.toLocaleString("es-BO");
    } catch (error) {
        return "no disponible";
    }
}

function formatearConfianza(confianza) {
    if (confianza === null || confianza === undefined) return "no disponible";

    const valor = Number(confianza);
    if (Number.isNaN(valor)) return "no disponible";

    if (valor <= 1) return `${(valor * 100).toFixed(1)}%`;
    return `${valor.toFixed(1)}%`;
}

function formatearNumero(valor, decimales = 2) {
    if (valor === null || valor === undefined) return "no disponible";

    const numero = Number(valor);
    if (Number.isNaN(numero)) return "no disponible";

    return numero.toFixed(decimales);
}

function crearPopupBache(bache) {
    const imagenHTML = bache.imagen_url
        ? `
            <div style="margin-top:12px; text-align:center;">
                <img 
                    src="${bache.imagen_url}" 
                    alt="Imagen anotada del bache"
                    style="
                        width:100%;
                        max-width:280px;
                        border-radius:10px;
                        border:1px solid #ccc;
                        box-shadow:0 2px 8px rgba(0,0,0,0.15);
                    "
                >
            </div>
          `
        : "";

    return `
        <div style="font-family:Arial, sans-serif; min-width:250px; max-width:290px; font-size:13px;">
            <h3 style="margin:0 0 10px 0; color:#111827;">Bache detectado</h3>

            <p style="margin:4px 0;"><b>Tipo de detección:</b> ${nombreTipoDeteccion(bache.tipo_deteccion)}</p>
            <p style="margin:4px 0;"><b>Severidad:</b> ${bache.severidad ?? "no definida"}</p>
            <p style="margin:4px 0;"><b>Confianza:</b> ${formatearConfianza(bache.confianza)}</p>
            <p style="margin:4px 0;"><b>Profundidad:</b> ${formatearNumero(bache.profundidad_mm, 1)} mm</p>
            <p style="margin:4px 0;"><b>Área:</b> ${formatearNumero(bache.area_m2, 3)} m²</p>
            <p style="margin:4px 0;"><b>Latitud:</b> ${bache.lat ?? "no disponible"}</p>
            <p style="margin:4px 0;"><b>Longitud:</b> ${bache.lon ?? "no disponible"}</p>
            <p style="margin:4px 0;"><b>Fecha:</b> ${formatearFecha(bache.fecha)}</p>
            <p style="margin:4px 0;"><b>RUN ID:</b> ${bache.run_id ?? "no disponible"}</p>
            <p style="margin:4px 0; word-break:break-all;"><b>Frame:</b> ${bache.frame ?? "no disponible"}</p>

            ${imagenHTML}
        </div>
    `;
}

function obtenerSeleccionados(clase) {
    return Array.from(document.querySelectorAll(`.${clase}:checked`)).map(input => input.value);
}

function filtrarDatos() {
    const severidades = obtenerSeleccionados("filtro-severidad");
    const tipos = obtenerSeleccionados("filtro-tipo");

    return todosLosBaches.filter(bache => {
        const pasaSeveridad =
            severidades.length === 0 || severidades.includes(bache.severidad);

        const pasaTipo =
            tipos.length === 0 || tipos.includes(bache.tipo_deteccion);

        return pasaSeveridad && pasaTipo;
    });
}

function limpiarCapas() {
    if (map.hasLayer(clusterGroup)) {
        map.removeLayer(clusterGroup);
    }

    clusterGroup.clearLayers();

    if (heatLayer) {
        map.removeLayer(heatLayer);
        heatLayer = null;
    }
}

function contarEnPantalla() {
    const bounds = map.getBounds();
    let visibles = 0;

    bachesGlobal.forEach(bache => {
        if (
            typeof bache.lat === "number" &&
            typeof bache.lon === "number" &&
            bounds.contains([bache.lat, bache.lon])
        ) {
            visibles++;
        }
    });

    return visibles;
}

function actualizarResumen() {
    const resumen = document.getElementById("resumen");

    const total = bachesGlobal.length;
    const visibles = contarEnPantalla();

    const severidades = obtenerSeleccionados("filtro-severidad");
    const tipos = obtenerSeleccionados("filtro-tipo");

    const severidadTexto =
        severidades.length > 0
            ? severidades.join(", ")
            : "todas";

    const tipoTexto =
        tipos.length > 0
            ? tipos.map(nombreTipoDeteccion).join(", ")
            : "todos";

    resumen.innerHTML = `
        <div class="chips-resumen">

            <div class="chip-resumen">
                <span class="chip-label">Total</span>
                <span class="chip-valor">${total}</span>
            </div>

            <div class="chip-resumen">
                <span class="chip-label">En pantalla</span>
                <span class="chip-valor">${visibles}</span>
            </div>

            <div class="chip-resumen">
                <span class="chip-label">Severidad</span>
                <span class="chip-valor">${severidadTexto}</span>
            </div>

            <div class="chip-resumen">
                <span class="chip-label">Tipo</span>
                <span class="chip-valor">${tipoTexto}</span>
            </div>

            <div class="chip-resumen">
                <span class="chip-label">Modo</span>
                <span class="chip-valor">${modoVisualizacion === "calor" ? "Mapa de calor" : "Marcadores"}</span>
            </div>

        </div>
    `;
}

function dibujarMarcadores(baches) {
    limpiarCapas();

    const bounds = [];

    baches.forEach(bache => {
        if (typeof bache.lat !== "number" || typeof bache.lon !== "number") return;

        const color = obtenerColor(bache.severidad);

        const marcador = L.circleMarker([bache.lat, bache.lon], {
            radius: 8,
            color: color,
            fillColor: color,
            fillOpacity: 0.8
        }).bindPopup(crearPopupBache(bache));

        clusterGroup.addLayer(marcador);
        bounds.push([bache.lat, bache.lon]);
    });

    map.addLayer(clusterGroup);

    if (bounds.length > 0) {
        map.fitBounds(bounds, { padding: [50, 50] });
    }

    actualizarResumen();
}

function dibujarMapaCalor(baches) {
    limpiarCapas();

    const puntosCalor = baches
        .filter(bache => typeof bache.lat === "number" && typeof bache.lon === "number")
        .map(bache => [
            bache.lat,
            bache.lon,
            pesoSeveridad(bache.severidad)
        ]);

    if (puntosCalor.length > 0) {
        heatLayer = L.heatLayer(puntosCalor, {
            radius: 30,
            blur: 22,
            maxZoom: 17
        }).addTo(map);

        const bounds = puntosCalor.map(p => [p[0], p[1]]);
        map.fitBounds(bounds, { padding: [50, 50] });
    }

    actualizarResumen();
}

function renderizarMapa() {
    bachesGlobal = filtrarDatos();

    if (modoVisualizacion === "calor") {
        dibujarMapaCalor(bachesGlobal);
    } else {
        dibujarMarcadores(bachesGlobal);
    }
}

async function obtenerBachesFirestore() {
    const querySnapshot = await getDocs(collection(db, "baches"));
    const baches = [];

    querySnapshot.forEach((doc) => {
        baches.push({
            id: doc.id,
            ...doc.data()
        });
    });

    return baches;
}

async function cargarDatosIniciales() {
    try {
        todosLosBaches = await obtenerBachesFirestore();
        renderizarMapa();
    } catch (error) {
        console.error("Error Firestore:", error);
        alert("Error al leer Firestore");
    }
}

function aplicarFiltros() {
    renderizarMapa();
}

function limpiarFiltros() {
    document.querySelectorAll(".filtro-severidad, .filtro-tipo").forEach(input => {
        input.checked = false;
    });

    renderizarMapa();
}

function cambiarModoVisualizacion(modo) {
    modoVisualizacion = modo;

    document.getElementById("btnModoMarcadores").classList.toggle("activo", modo === "marcadores");
    document.getElementById("btnModoCalor").classList.toggle("activo", modo === "calor");

    renderizarMapa();
}

function toggleSidebar() {
    const sidebar = document.getElementById("sidebarFiltros");
    sidebar.classList.toggle("cerrado");

    setTimeout(() => {
        map.invalidateSize();
    }, 300);
}

function inicializarUbicacionUsuario() {
    if (!navigator.geolocation) {
        map.setView(COCHABAMBA, 15);
        return;
    }

    navigator.geolocation.getCurrentPosition(
        (position) => {
            const lat = position.coords.latitude;
            const lon = position.coords.longitude;

            map.setView([lat, lon], 15);

            if (marcadorUsuario) {
                map.removeLayer(marcadorUsuario);
            }

            marcadorUsuario = L.marker([lat, lon], { icon: iconoUsuario })
                .addTo(map)
                .bindPopup("Tu ubicación actual");
        },
        () => {
            map.setView(COCHABAMBA, 15);
        }
    );
}

window.aplicarFiltros = aplicarFiltros;
window.limpiarFiltros = limpiarFiltros;
window.cambiarModoVisualizacion = cambiarModoVisualizacion;
window.toggleSidebar = toggleSidebar;

map.on("moveend", () => {
    actualizarResumen();
});

inicializarUbicacionUsuario();
cargarDatosIniciales();

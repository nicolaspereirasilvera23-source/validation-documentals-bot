'use strict';

/* ==========================================================================
   Consulta de Carné del Deportista — lógica de la interfaz
   ========================================================================== */

const form = document.getElementById('form');
const area = document.getElementById('cedulas');
const diasInput = document.getElementById('dias');
const boton = document.getElementById('consultar');
const botonLimpiar = document.getElementById('limpiar');
const estadoPeticion = document.getElementById('estado-peticion');
const resumen = document.getElementById('resumen');
const mensajes = document.getElementById('mensajes');
const resultados = document.getElementById('resultados');



const tplVacio = document.getElementById('tpl-vacio');
const aceptarTerminos = document.getElementById('aceptar-terminos');
const condiciones = document.getElementById('condiciones');
const confirmarTerminos = document.getElementById('confirmar-terminos');
const sistema = document.getElementById('sistema');
let condicionesAceptadas = false;
let consultaActiva = null;


const CLASES_ESTADO = {
  'En fecha': 'en-fecha',
  'Pronto a vencer': 'pronto',
  'Vencido': 'vencido',
  'Sin fecha': 'sin-fecha',
};



/* ------------------------------- Utilidades ------------------------------ */

function nodo(etiqueta, clase, texto) {
  const elemento = document.createElement(etiqueta);
  if (clase) elemento.className = clase;
  if (texto !== undefined) elemento.textContent = texto;
  return elemento;
}

function contarCedulas(texto) {
  return texto
    .split(/[,;\s]+/)
    .map((parte) => parte.trim())
    .filter(Boolean).length;
}

function formatearFecha(iso) {
  if (!iso) return '—';
  const [anio, mes, dia] = iso.split('-');
  return `${dia}/${mes}/${anio}`;
}

function textoDias(carne) {
  if (carne.dias_restantes === null || carne.dias_restantes === undefined) {
    return 'Sin fecha de vencimiento';
  }
  const dias = carne.dias_restantes;
  if (dias === 0) return 'Vence hoy';
  if (dias > 0) return dias === 1 ? 'Vence en 1 día' : `Vence en ${dias} días`;
  const pasados = Math.abs(dias);
  return pasados === 1 ? 'Venció hace 1 día' : `Venció hace ${pasados} días`;
}

function mostrarEstado(texto, tipo = '') {
  estadoPeticion.textContent = texto;
  estadoPeticion.className = 'estado-peticion' + (tipo ? ` estado-peticion--${tipo}` : '');
}

/* ------------------------------- Render ---------------------------------- */

function crearAviso(tipo, titulo, items) {
  const caja = nodo('div', `aviso aviso--${tipo}`);
  const icono = nodo('span', 'aviso__icono', tipo === 'error' ? '!' : 'i');
  icono.setAttribute('aria-hidden', 'true');

  const cuerpo = nodo('div');
  cuerpo.append(nodo('p', 'aviso__titulo', titulo));

  const lista = document.createElement('ul');
  for (const item of items) {
    const elemento = document.createElement('li');
    if (typeof item === 'string') {
      elemento.textContent = item;
    } else {
      elemento.textContent = item.principal;
      if (item.detalle) {
        elemento.append(nodo('span', '', ` — ${item.detalle}`));
      }
    }
    lista.append(elemento);
  }
  cuerpo.append(lista);

  caja.append(icono, cuerpo);
  return caja;
}

function renderResumen(datos) {
  const carnes = datos.resultados || [];
  const sinResultados = datos.sin_resultados || [];
  resumen.replaceChildren();

  if (!carnes.length && !sinResultados.length) {
    resumen.hidden = true;
    return;
  }

  const conteo = { 'En fecha': 0, 'Pronto a vencer': 0, 'Vencido': 0, 'Sin fecha': 0 };
  for (const carne of carnes) {
    if (carne.estado in conteo) conteo[carne.estado] += 1;
  }

  const tarjetas = [
    { valor: carnes.length, etiqueta: 'Carnés', clase: '' },
    { valor: conteo['En fecha'], etiqueta: 'En fecha', clase: 'verde' },
    { valor: conteo['Pronto a vencer'], etiqueta: 'Pronto a vencer', clase: 'ambar' },
    { valor: conteo['Vencido'], etiqueta: 'Vencidos', clase: 'rojo' },
    { valor: sinResultados.length, etiqueta: 'Sin resultados', clase: 'gris' },
  ];

  for (const tarjeta of tarjetas) {
    const caja = nodo('div', `dato${tarjeta.clase ? ` dato--${tarjeta.clase}` : ''}`);
    caja.append(
      nodo('span', 'dato__valor', String(tarjeta.valor)),
      nodo('span', 'dato__etiqueta', tarjeta.etiqueta)
    );
    resumen.append(caja);
  }

  resumen.hidden = false;
}

function renderMensajes(datos) {
  mensajes.replaceChildren();
  const bloques = [];

  if (datos.invalidas && datos.invalidas.length) {
    bloques.push(
      crearAviso(
        'alerta',
        'Datos ignorados',
        datos.invalidas.map((valor) => ({
          principal: valor,
          detalle: 'no parece una cédula válida (se esperan 6 a 8 dígitos)',
        }))
      )
    );
  }

  if (datos.sin_resultados && datos.sin_resultados.length) {
    bloques.push(
      crearAviso(
        'alerta',
        'Sin resultados',
        datos.sin_resultados.map((item) => ({
          principal: item.cedula,
          detalle: item.mensaje,
        }))
      )
    );
  }

  if (datos.errores && datos.errores.length) {
    bloques.push(
      crearAviso(
        'error',
        'No se pudieron consultar',
        datos.errores.map((item) => ({
          principal: item.cedula,
          detalle: item.mensaje,
        }))
      )
    );
  }

  mensajes.replaceChildren(...bloques);
  mensajes.hidden = bloques.length === 0;
}

function crearFecha(etiqueta, iso) {
  const contenedor = document.createElement('span');
  contenedor.append(
    nodo('span', 'etiqueta', etiqueta),
    document.createTextNode(` ${formatearFecha(iso)}`)
  );
  return contenedor;
}

function crearCarne(carne) {
  const item = nodo('li', 'carne');

  const info = nodo('div', 'carne__info');
  info.append(nodo('span', 'carne__deporte', carne.deporte));

  const fechas = nodo('div', 'carne__fechas');
  fechas.append(crearFecha('Desde', carne.desde), crearFecha('Hasta', carne.hasta));
  info.append(fechas);

  const estado = nodo('div', 'carne__estado');
  const clase = CLASES_ESTADO[carne.estado] || 'sin-fecha';
  estado.append(
    nodo('span', `insignia insignia--${clase}`, carne.estado),
    nodo('span', 'carne__dias', textoDias(carne))
  );

  item.append(info, estado);
  return item;
}

function crearPersona(cedula, grupo) {
  const articulo = nodo('article', 'persona');

  const cabecera = nodo('header', 'persona__cabecera');
  cabecera.append(
    nodo('h2', 'persona__nombre', grupo.nombre),
    nodo('span', 'persona__cedula', cedula)
  );

  const lista = nodo('ul', 'carnes');
  for (const carne of grupo.carnes) lista.append(crearCarne(carne));

  articulo.append(cabecera, lista);
  return articulo;
}

function renderResultados(carnes) {
  resultados.replaceChildren();

  if (!carnes.length) {
    resultados.append(tplVacio.content.cloneNode(true));
    return;
  }

  const grupos = new Map();
  for (const carne of carnes) {
    if (!grupos.has(carne.cedula)) {
      grupos.set(carne.cedula, { nombre: carne.nombre, carnes: [] });
    }
    grupos.get(carne.cedula).carnes.push(carne);
  }

  for (const [cedula, grupo] of grupos) {
    resultados.append(crearPersona(cedula, grupo));
  }
}

function render(datos) {
  renderResumen(datos);
  renderMensajes(datos);
  renderResultados(datos.resultados || []);

  const total = (datos.resultados || []).length;
  if (total) {
    mostrarEstado(
      `Consultado el ${datos.consultado} · criterio de aviso ≤ ${datos.dias_aviso} días`,
      'ok'
    );
  } else {
    mostrarEstado(`Consultado el ${datos.consultado} · no se encontraron carnés.`);
  }
}

/* ------------------------------- Acciones -------------------------------- */

function bloquear(activo) {
  boton.disabled = activo;
  boton.classList.toggle('boton--cargando', activo);
  boton.querySelector('.boton__texto').textContent = activo ? 'Consultando…' : 'Consultar';
}

async function consultar(evento) {
  evento.preventDefault();

  if (consultaActiva) return;
  if (!condicionesAceptadas) {
    mostrarEstado('Leé y aceptá las condiciones antes de consultar.', 'error');
    aceptarTerminos.focus();
    return;
  }

  const texto = area.value.trim();
  if (!texto) {
    mostrarEstado('Ingresá al menos una cédula para consultar.', 'error');
    area.focus();
    return;
  }

  const cantidad = contarCedulas(texto);
  bloquear(true);
  mostrarEstado(`Consultando ${cantidad} cédula${cantidad === 1 ? '' : 's'}…`);

  const controlador = new AbortController();
  consultaActiva = controlador;
  try {
    const respuesta = await fetch('/api/consulta', {
      method: 'POST',
      cache: 'no-store',
      signal: controlador.signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cedulas: texto,
        dias_aviso: Number(diasInput.value) || 0,
      }),
    });

    const datos = await respuesta.json().catch(() => ({}));
    if (!respuesta.ok) {
      throw new Error(datos.error || `El servidor respondió HTTP ${respuesta.status}.`);
    }
    if (controlador.signal.aborted) return;
    area.value = '';
    render(datos);
  } catch (error) {
    if (controlador.signal.aborted) return;
    mostrarEstado(`No se pudo completar la consulta: ${error.message}`, 'error');
  } finally {
    if (consultaActiva === controlador) consultaActiva = null;
    bloquear(false);
  }
}

function limpiarTodo() {
  if (consultaActiva) consultaActiva.abort();
  area.value = '';
  resultados.replaceChildren(tplVacio.content.cloneNode(true));
  mensajes.replaceChildren();
  mensajes.hidden = true;
  resumen.replaceChildren();
  resumen.hidden = true;
  mostrarEstado('');
  area.focus();
}

/* --------------------------------- Init ---------------------------------- */

form.addEventListener('submit', consultar);
aceptarTerminos.addEventListener('change', () => {
  confirmarTerminos.disabled = !aceptarTerminos.checked;
});
botonLimpiar.addEventListener('click', limpiarTodo);
confirmarTerminos.addEventListener('click', () => {
  if (!aceptarTerminos.checked) return;
  condicionesAceptadas = true;
  condiciones.close();
  sistema.inert = false;
  area.focus();
});
condiciones.addEventListener('cancel', (evento) => evento.preventDefault());

area.addEventListener('keydown', (evento) => {
  if ((evento.ctrlKey || evento.metaKey) && evento.key === 'Enter') {
    evento.preventDefault();
    form.requestSubmit();
  }
});

// Elimina preferencias y cédulas que pudieran conservar versiones anteriores.
try {
  localStorage.removeItem('carnes.cedulas');
  localStorage.removeItem('carnes.dias');
} catch (_) { /* almacenamiento no disponible */ }
function pedirAceptacion() {
  condicionesAceptadas = false;
  aceptarTerminos.checked = false;
  confirmarTerminos.disabled = true;
  sistema.inert = true;
  if (condiciones.open) condiciones.close();
  condiciones.showModal();
}
window.addEventListener('pagehide', () => {
  limpiarTodo();
  diasInput.value = '30';
  condicionesAceptadas = false;
});
window.addEventListener('pageshow', (evento) => {
  if (evento.persisted) pedirAceptacion();
});
pedirAceptacion();
resultados.replaceChildren(tplVacio.content.cloneNode(true));


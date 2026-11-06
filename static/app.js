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
const barraAcciones = document.getElementById('barra-acciones');
const botonDescargar = document.getElementById('descargar');
const notaDescarga = document.getElementById('nota-descarga');
const tplVacio = document.getElementById('tpl-vacio');
const aceptarTerminos = document.getElementById('aceptar-terminos');

const CLAVES = { dias: 'carnes.dias' };
const CLASES_ESTADO = {
  'En fecha': 'en-fecha',
  'Pronto a vencer': 'pronto',
  'Vencido': 'vencido',
  'Sin fecha': 'sin-fecha',
};

let ultimaRespuesta = null;

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

function guardarPreferencias() {
  try {
    localStorage.setItem(CLAVES.dias, diasInput.value);
  } catch (_) {
    /* almacenamiento no disponible (modo privado) */
  }
}

function restaurarPreferencias() {
  try {
    // Borra cédulas guardadas por versiones anteriores de la interfaz.
    localStorage.removeItem('carnes.cedulas');
    const dias = localStorage.getItem(CLAVES.dias);
    if (dias !== null && dias !== '') diasInput.value = dias;
  } catch (_) {
    /* sin almacenamiento */
  }
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
  ultimaRespuesta = datos;
  renderResumen(datos);
  renderMensajes(datos);
  renderResultados(datos.resultados || []);

  const total = (datos.resultados || []).length;
  barraAcciones.hidden = total === 0;
  if (total) {
    notaDescarga.textContent = `${total} carné${total === 1 ? '' : 's'} · ${datos.consultado}`;
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

  if (!aceptarTerminos.checked) {
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

  guardarPreferencias();
  const cantidad = contarCedulas(texto);
  bloquear(true);
  mostrarEstado(`Consultando ${cantidad} cédula${cantidad === 1 ? '' : 's'}…`);

  try {
    const respuesta = await fetch('/api/consulta', {
      method: 'POST',
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
    render(datos);
  } catch (error) {
    mostrarEstado(`No se pudo completar la consulta: ${error.message}`, 'error');
  } finally {
    bloquear(false);
  }
}

function limpiarTodo() {
  area.value = '';
  resultados.replaceChildren(tplVacio.content.cloneNode(true));
  mensajes.replaceChildren();
  mensajes.hidden = true;
  resumen.replaceChildren();
  resumen.hidden = true;
  barraAcciones.hidden = true;
  ultimaRespuesta = null;
  mostrarEstado('');
  area.focus();
}

function campoCSV(valor) {
  const texto = valor === null || valor === undefined ? '' : String(valor);
  return /[";\r\n]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto;
}

function descargarCSV() {
  const carnes = (ultimaRespuesta && ultimaRespuesta.resultados) || [];
  if (!carnes.length) return;

  const columnas = ['cedula', 'nombre', 'deporte', 'desde', 'hasta', 'dias_restantes', 'estado'];
  const filas = [columnas];
  for (const carne of carnes) {
    filas.push([
      carne.cedula,
      carne.nombre,
      carne.deporte,
      carne.desde || '',
      carne.hasta || '',
      carne.dias_restantes ?? '',
      carne.estado,
    ]);
  }

  const contenido =
    '\uFEFF' + filas.map((fila) => fila.map(campoCSV).join(';')).join('\r\n');

  const ahora = new Date();
  const sello = [
    ahora.getFullYear(),
    String(ahora.getMonth() + 1).padStart(2, '0'),
    String(ahora.getDate()).padStart(2, '0'),
  ].join('');

  const enlace = document.createElement('a');
  const url = URL.createObjectURL(new Blob([contenido], { type: 'text/csv;charset=utf-8;' }));
  enlace.href = url;
  enlace.download = `carnes_${sello}.csv`;
  document.body.append(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/* --------------------------------- Init ---------------------------------- */

form.addEventListener('submit', consultar);
aceptarTerminos.addEventListener('change', () => {
  if (aceptarTerminos.checked) mostrarEstado('');
});
botonLimpiar.addEventListener('click', limpiarTodo);
botonDescargar.addEventListener('click', descargarCSV);

area.addEventListener('keydown', (evento) => {
  if ((evento.ctrlKey || evento.metaKey) && evento.key === 'Enter') {
    evento.preventDefault();
    form.requestSubmit();
  }
});

restaurarPreferencias();
resultados.replaceChildren(tplVacio.content.cloneNode(true));

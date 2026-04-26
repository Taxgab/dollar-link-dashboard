# Design System — Dollar Link Dashboard

## Conceptual Direction

**Terminal de Trading Neoclásica Argentina**

Un híbrido entre la crudeza matemática de una terminal financiera y la elegancia institucional de un banco centenario. El producto no quiere verse como un SaaS genérico; quiere transmitir autoridad, velocidad y contexto cultural argentino. Es información de mercado presentada con la solemnidad que el dinero merece.

**Palabras clave**: oscuro, preciso, dorado, institucional, matemático, porteño, sobrio, premium.

---

## Color System

| Token | Valor | Uso |
|-------|-------|-----|
| `--bg-void` | `#030303` | Fondo raíz del documento. Casi negro, absorbe luz. |
| `--bg-surface` | `#0a0a0f` | Cards, filas de tabla, contenedores. Un paso sobre el void. |
| `--bg-elevated` | `#111118` | Estado hover, elementos elevados. Mínimo contraste, suficiente para leer profundidad. |
| `--glass` | `rgba(255,255,255,0.03)` | Fondos translúcidos de contexto (REM/BADLAR banners). |
| `--border` | `rgba(255,255,255,0.08)` | Divisores estándar. Casi invisibles, estructuran sin gritar. |
| `--border-strong` | `rgba(255,255,255,0.15)` | Bordes en estado hover o enfocado. |
| `--text-primary` | `#e2e8f0` | Texto principal. Blanco ahumado, no blanco puro. |
| `--text-secondary` | `#475569` | Labels, metadatos, timestamps. Gris frío. |
| `--text-muted` | `#334155` | Líneas divisorias de texto, acentos mínimos. |
| `--gold` | `#d4af37` | Acento primario de prestige. Símbolos, proyecciones, hover activo. Oro antiguo, no amarillo. |
| `--gold-dim` | `rgba(212,175,55,0.15)` | Glows y fondos dorados sutiles. |
| `--green` | `#4ade80` | Variación positiva. Verde ácido con glow sutil. |
| `--green-dim` | `rgba(74,222,128,0.1)` | Halo de glow para valores verdes. |
| `--red` | `#f87171` | Variación negativa. Rojo sangre. |
| `--red-dim` | `rgba(248,113,113,0.1)` | Halo de glow para valores rojos. |
| `--blue` | `#60a5fa` | Datos neutrales/CCL. Azul hielo. |

**Atmósfera de fondo**:
- Dos gradientes radiales difusos (dorado a 4% opacidad arriba-izquierda, azul a 3% abajo-derecha).
- Dot grid de 32px con puntos al 3% de opacidad.
- Sin imágenes, sin ilustraciones. Todo el drama es tipográfico y espacial.

---

## Typography

| Rol | Familia | Peso | Uso |
|-----|---------|------|-----|
| Display | `Playfair Display` (serif) | 700 | Título principal "Dollar Link". Transmite peso institucional y elegancia editorial. |
| UI / Body | `Outfit` (sans-serif) | 400-600 | Labels, badges, botones, navegación. Geométrica, limpia, moderna. |
| Data / Mono | `JetBrains Mono` | 300-700 | Todos los números, timestamps, tickers, tablas. Monospace matemática, legible en densidad. |

**Escala tipográfica**:
- Título: `2.8rem` / `letter-spacing: -0.02em`
- Badges/tags: `0.6rem` / `letter-spacing: 0.1em` / uppercase
- Tabla de datos: `0.85rem`
- Labels de sección: `0.65rem` / `letter-spacing: 0.15em` / uppercase

**Regla**: Nunca se usa Arial, Inter, Roboto o system fonts. La identidad tipográfica es innegociable.

---

## Spacing & Layout

- **Container**: `max-width: 1400px`, centrado, `padding: 40px 24px`.
- **Secciones**: Separadas por `margin-bottom: 40px` o `48px`.
- **FX Grid**: `1px` de gap entre cards, creando una superficie continua partida por líneas (estilo panel Bloomberg).
- **Tabla**: `border-spacing: 0 6px` entre filas. Cada fila es una unidad independiente con bordes redondeados.

**Composición**:
- Header asimétrico: marca grande a la izquierda, status a la derecha.
- No hay sidebars ni navs. Todo es vertical y directo.
- El footer es minimalista, casi un afterthought técnico.

---

## Component Anatomy

### FX Card
- Fondo: `var(--bg-surface)`
- Padding: `24px`
- Separador: `1px` vertical entre cards (`::after` pseudo-elemento)
- Hover: fondo eleva a `--bg-elevated`
- Sin sombra, sin border-radius individual. El border-radius es del contenedor grid.

### Context Banner (REM / BADLAR)
- Fondo: `var(--glass)` + `backdrop-filter: blur(8px)`
- Borde: `1px solid var(--border)`
- Línea lateral de acento: `3px` de ancho (azul para REM, oro para BADLAR)
- Layout: stats horizontales con label/value apilados

### Table Row
- Fondo: `var(--bg-surface)`
- Bordes: `1px solid var(--border)`, `border-radius: 8px`
- Hover: `translateX(6px)`, sombra lateral dorada (`-4px 0 0 var(--gold-dim)`), fondo eleva.
- Transición: `0.3s cubic-bezier(0.4, 0, 0.2, 1)`

### Chart Container
- Fondo: `var(--bg-surface)`
- Borde: `1px solid var(--border)`
- Border-radius: `12px`
- Padding: `24px`
- Altura fija: `380px`

---

## Motion & Animation

**Filosofía**: El movimiento es información. Una interfaz de mercado debe sentirse viva, pero nunca distraer de los números.

| Animación | Detalle |
|-----------|---------|
| Page load | Staggered `fadeInUp` (0s, 0.1s, 0.2s, 0.3s, 0.4s, 0.5s) por sección. |
| Live indicator | `pulse` infinito (2s) en el punto verde del status. |
| Row hover | `translateX(6px)` + sombra dorada lateral. Movimiento lateral, no vertical, para sugerir lectura de ticker. |
| Button hover | Border y color transicionan a oro. Sin transformaciones. |
| Data refresh | Los números actualizan instantáneamente. No hay animación de conteo (esos son juegos; esto es mercado). |
| Chart tooltip | Fade-in instantáneo, fondo oscuro, bordes dorados en el título. |

---

## Responsive Behavior

**Desktop (>900px)**:
- FX grid: 4 columnas.
- Context banners: lado a lado.
- Tabla: layout completo con 13 columnas.
- Chart: altura completa (380px).

**Tablet (640px - 900px)**:
- FX grid: 2 columnas.
- Context banners: apilados.
- Título reduce a `2rem`.

**Mobile (<640px)**:
- FX grid: 1 columna.
- Header apilado verticalmente.
- Tabla: cada fila se convierte en tarjeta apilada usando `data-label` para mostrar headers inline.
- Chart: mantiene proporción pero reduce altura automáticamente por `maintainAspectRatio: false` en contenedor relativo.

---

## Chart Design

**Tipo**: Línea (Line Chart) con puntos discretos.
**Datasets**:
1. **Valor Actual (ARS)**: Línea sólida gris (`#475569`). Representa el estado nominal.
2. **Proyección REM 12m (ARS)**: Línea punteada dorada (`#d4af37`). Representa el valor teórico ajustado por expectativas de inflación.

**Estilo**:
- Fondo del canvas: transparente (hereda `--bg-surface`).
- Grid: solo horizontal, `rgba(255,255,255,0.03)`.
- Ejes: ticks en `JetBrains Mono`, color `var(--text-secondary)`.
- Tooltip: fondo `--bg-surface`, borde `1px`, título dorado.
- Leyenda: `usePointStyle: true` para un look limpio.

---

## Assets & Dependencies

- **Google Fonts**: Playfair Display, Outfit, JetBrains Mono.
- **Chart.js**: v4.4.1 (CDN).
- **Sin imágenes**, **sin SVGs decorativos**, **sin icon libraries**. Todo es CSS puro y tipografía.

---

## Design Principles (para futuras modificaciones)

1. **Oscuridad como default**: La luz debe provenir de los datos, no del fondo. Los números son las estrellas.
2. **Oro es un acento, no un tema**: El dorado se reserva para lo teórico, proyectado, premium. El gris/blanco es para lo factual.
3. **Monospace para todo número**: Nunca uses Outfit o Playfair para mostrar un precio. Los números necesitan alineación tabular.
4. **Animaciones laterales, no verticales**: El mercado se lee de izquierda a derecha. El movimiento UI debe respetar esa dirección.
5. **Menos es más que más**: Si algo no justifica su espacio visual, se elimina. No hay gráficos decorativos, no hay ilustraciones de banderas, no hay emojis en el dashboard principal.

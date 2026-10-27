import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';
import { CATEGORIES, GNode, Graphe } from './reseau.models';

interface PNode extends GNode { x: number; y: number; color: string; side: 'left' | 'mid' | 'right'; }
interface PEdge { a: PNode; b: PNode; relations: string[]; path: string; color: string; dashed: string | null; }

const W = 1000;
const ROW = 58;
const PAD = 46;

const RELATIONS: Record<string, { color: string; dash: string | null; label: string }> = {
  relie: { color: 'var(--reseau)', dash: null, label: 'relie (ligne → poste)' },
  estConnecteA: { color: 'var(--reseau)', dash: '2 5', label: 'estConnecteA (symétrique)' },
  transporteVers: { color: 'var(--batiments)', dash: null, label: 'transporteVers / estRaccordeA' },
  estRaccordeA: { color: 'var(--batiments)', dash: null, label: '' },
  injecteDans: { color: 'var(--production)', dash: '7 5', label: 'injecteDans (source → ligne)' },
};

/** Vue du réseau en trois colonnes : postes | lignes | sources et bâtiments. */
@Component({
  selector: 'app-reseau-graphe',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="legend">
      <span><i class="dot" style="background: var(--reseau)"></i>Poste</span>
      <span><i class="dia" style="background: var(--reseau)"></i>Ligne (HT / MT / BT)</span>
      <span><i class="dot" style="background: var(--batiments)"></i>Bâtiment</span>
      <span><i class="dot" style="background: var(--production)"></i>Source</span>
      @for (r of legend; track r.label) {
        <span><svg width="26" height="8"><line x1="0" y1="4" x2="26" y2="4" [attr.stroke]="r.color" stroke-width="2" [attr.stroke-dasharray]="r.dash"/></svg>{{ r.label }}</span>
      }
    </div>

    <div class="scroll">
      <svg [attr.viewBox]="'0 0 ' + W + ' ' + layout().h" class="graph" role="img" aria-label="Graphe du réseau électrique">
        <g class="cols">
          <text [attr.x]="230" y="22">POSTES</text>
          <text [attr.x]="500" y="22">LIGNES</text>
          <text [attr.x]="790" y="22">SOURCES · BÂTIMENTS</text>
        </g>

        @for (e of layout().edges; track $index) {
          <path [attr.d]="e.path" fill="none" [attr.stroke]="e.color" [attr.stroke-dasharray]="e.dashed"
                stroke-width="1.8" class="edge" [class.dim]="isDim(e)" [class.hot]="isHot(e)">
            <title>{{ e.a.label }} — {{ e.relations.join(', ') }} — {{ e.b.label }}</title>
          </path>
        }

        @for (n of layout().nodes; track n.id) {
          <g class="node" [class.dim]="hover() && !related().has(n.id)"
             (mouseenter)="hover.set(n.id)" (mouseleave)="hover.set(null)" (focus)="hover.set(n.id)" (blur)="hover.set(null)" tabindex="0">
            <title>{{ n.label }} (sg:{{ n.id }})</title>
            @if (n.type === 'ligne') {
              <rect [attr.x]="n.x - 9" [attr.y]="n.y - 9" width="18" height="18" rx="3"
                    [attr.transform]="'rotate(45 ' + n.x + ' ' + n.y + ')'" [attr.fill]="n.color" />
              <text [attr.x]="n.x" [attr.y]="n.y - 17" text-anchor="middle" class="lbl">{{ short(n.label) }}</text>
              <text [attr.x]="n.x" [attr.y]="n.y + 25" text-anchor="middle" class="sub">{{ n.categorie }} · {{ n.tension }} kV</text>
            } @else {
              <circle [attr.cx]="n.x" [attr.cy]="n.y" [attr.r]="n.type === 'poste' ? 11 : 8" [attr.fill]="n.color" />
              @if (n.side === 'left') {
                <!-- libellé au-dessus : les arcs estConnecteA passent à gauche -->
                <text [attr.x]="n.x" [attr.y]="n.y - 18" text-anchor="middle" class="lbl">{{ short(n.label) }}</text>
              } @else {
                <text [attr.x]="n.x + 16" [attr.y]="n.y + 4" class="lbl">{{ short(n.label) }}</text>
              }
            }
          </g>
        }
      </svg>
    </div>`,
  styles: [`
    :host { display: grid; gap: 14px; }
    .legend { display: flex; flex-wrap: wrap; gap: 8px 18px; font-size: 12.5px; color: var(--muted); }
    .legend span { display: inline-flex; align-items: center; gap: 7px; }
    .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    .dia { width: 9px; height: 9px; transform: rotate(45deg); border-radius: 2px; display: inline-block; }
    .scroll { overflow-x: auto; }
    .graph { width: 100%; min-width: 720px; height: auto; display: block; }
    .cols text { font-size: 11px; font-weight: 700; letter-spacing: .14em; fill: var(--muted); text-anchor: middle; }
    .edge { opacity: .55; transition: opacity var(--t), stroke-width var(--t); }
    .edge.hot { opacity: 1; stroke-width: 2.6; }
    .edge.dim { opacity: .08; }
    .node { cursor: default; outline: none; transition: opacity var(--t); }
    .node.dim { opacity: .2; }
    .lbl { font-size: 13px; font-weight: 600; fill: var(--text); }
    .sub { font-size: 11px; font-family: var(--mono); fill: var(--muted); }
  `],
})
export class ReseauGrapheComponent {
  data = input.required<Graphe>();
  hover = signal<string | null>(null);
  W = W;
  legend = Object.values(RELATIONS).filter(r => r.label);

  layout = computed(() => {
    const { nodes, edges } = this.data();
    const left = nodes.filter(n => n.type === 'poste');
    const mid = nodes.filter(n => n.type === 'ligne');
    const right = [...nodes.filter(n => n.type === 'source'), ...nodes.filter(n => n.type === 'batiment')];
    const rows = Math.max(left.length, mid.length, right.length, 1);
    const h = PAD * 2 + rows * ROW;

    const place = (list: GNode[], x: number, side: PNode['side']): PNode[] => {
      const top = PAD + 10 + (rows - list.length) * ROW / 2;
      return list.map((n, i) => ({ ...n, x, y: top + i * ROW + ROW / 2, side, color: this.color(n) }));
    };
    const placed = [...place(left, 230, 'left'), ...place(mid, 500, 'mid'), ...place(right, 760, 'right')];
    const byId = new Map(placed.map(n => [n.id, n]));

    // une seule arête par paire de nœuds (transporteVers et estRaccordeA se recouvrent souvent)
    const merged = new Map<string, PEdge>();
    for (const e of edges) {
      const a = byId.get(e.source), b = byId.get(e.target);
      if (!a || !b) continue;
      const key = [a.id, b.id].sort().join('|');
      const existing = merged.get(key);
      if (existing) {
        if (!existing.relations.includes(e.relation)) existing.relations.push(e.relation);
        continue;
      }
      const style = RELATIONS[e.relation] ?? { color: 'var(--muted)', dash: null };
      merged.set(key, { a, b, relations: [e.relation], path: this.path(a, b), color: style.color, dashed: style.dash });
    }
    return { nodes: placed, edges: [...merged.values()], h };
  });

  related = computed(() => {
    const id = this.hover();
    const set = new Set<string>();
    if (!id) return set;
    set.add(id);
    for (const e of this.layout().edges) {
      if (e.a.id === id) set.add(e.b.id);
      if (e.b.id === id) set.add(e.a.id);
    }
    return set;
  });

  isHot(e: PEdge) { const h = this.hover(); return !!h && (e.a.id === h || e.b.id === h); }
  isDim(e: PEdge) { return !!this.hover() && !this.isHot(e); }

  short(label: string) { return label.length > 30 ? label.slice(0, 28) + '…' : label; }

  private color(n: GNode) {
    switch (n.type) {
      case 'ligne': return CATEGORIES[n.categorie ?? 'MT'].color;
      case 'batiment': return 'var(--batiments)';
      case 'source': return 'var(--production)';
      default: return 'var(--reseau)';
    }
  }

  private path(a: PNode, b: PNode) {
    if (a.side === b.side) {
      // estConnecteA entre deux postes : arc vers l'extérieur de la colonne
      const bulge = a.side === 'left' ? -110 : 110;
      return `M ${a.x} ${a.y} C ${a.x + bulge} ${a.y}, ${b.x + bulge} ${b.y}, ${b.x} ${b.y}`;
    }
    const [p, q] = a.x < b.x ? [a, b] : [b, a];
    const mx = (p.x + q.x) / 2;
    return `M ${p.x} ${p.y} C ${mx} ${p.y}, ${mx} ${q.y}, ${q.x} ${q.y}`;
  }
}

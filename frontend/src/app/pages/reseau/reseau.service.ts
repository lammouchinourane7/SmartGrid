import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import {
  Graphe, Ligne, LigneFiltres, LigneForm, ListResponse, MutationResponse,
  NlpReponse, Options, Poste, PosteForm, Stats,
} from './reseau.models';

/** Appels REST vers backend/modules/reseau (Flask + RDFLib). */
@Injectable({ providedIn: 'root' })
export class ReseauService {
  private http = inject(HttpClient);
  private base = '/api/reseau';

  stats() { return this.http.get<Stats>(`${this.base}/stats`); }
  options() { return this.http.get<Options>(`${this.base}/options`); }
  graphe() { return this.http.get<Graphe>(`${this.base}/graphe`); }

  lignes(f: LigneFiltres = {}) {
    let params = new HttpParams();
    if (f.q) params = params.set('q', f.q);
    if (f.categorie) params = params.set('categorie', f.categorie);
    if (f.tensionMin != null) params = params.set('tensionMin', f.tensionMin);
    if (f.tensionMax != null) params = params.set('tensionMax', f.tensionMax);
    if (f.poste) params = params.set('poste', f.poste);
    return this.http.get<ListResponse<Ligne>>(`${this.base}/lignes`, { params });
  }

  ligne(id: string) {
    return this.http.get<{ item: Ligne; sparql: string }>(`${this.base}/lignes/${id}`);
  }

  creerLigne(d: LigneForm) { return this.http.post<MutationResponse>(`${this.base}/lignes`, d); }
  modifierLigne(id: string, d: LigneForm) { return this.http.put<MutationResponse>(`${this.base}/lignes/${id}`, d); }
  supprimerLigne(id: string, force = false) {
    return this.http.delete<MutationResponse>(`${this.base}/lignes/${id}`, { params: force ? { force: 'true' } : {} });
  }

  postes(q = '') {
    return this.http.get<ListResponse<Poste>>(`${this.base}/postes`, { params: q ? { q } : {} });
  }

  creerPoste(d: PosteForm) { return this.http.post<MutationResponse>(`${this.base}/postes`, d); }
  modifierPoste(id: string, d: PosteForm) { return this.http.put<MutationResponse>(`${this.base}/postes/${id}`, d); }
  supprimerPoste(id: string, force = false) {
    return this.http.delete<MutationResponse>(`${this.base}/postes/${id}`, { params: force ? { force: 'true' } : {} });
  }

  question(question: string) { return this.http.post<NlpReponse>(`${this.base}/nlp`, { question }); }
  exemples() { return this.http.get<string[]>(`${this.base}/nlp/exemples`); }
}

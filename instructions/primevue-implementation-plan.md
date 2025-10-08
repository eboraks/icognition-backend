## iCognition Frontend Implementation Plan (PrimeVue)

This plan translates the two library UI screenshots in `instructions/icognition_library_1.png` and `instructions/icognition_library_2.png` into a concrete implementation using PrimeVue v4 components, PrimeFlex, and existing Vue 3 + Pinia routing. Reference: [PrimeVue Docs](https://primevue.org/).

### Goals
- Match the visuals and UX of the screenshots: Library view with and without a left filter panel, top bar actions, search, expandable document rows showing summary and key points, checkbox column, source links, and user menu.
- Standardize on PrimeVue components, themes, and utilities for consistency and speed.
- Keep routing and auth guards as-is; focus on view/component implementation and styling.

### Current Frontend Audit
- Vue 3, Vite, Pinia, Router present.
- PrimeVue already installed: `primevue@^4.3.9`, `@primevue/themes`, `primeflex`, `primeicons` (frontend/package.json).
- `src/main.ts` imports PrimeFlex and PrimeIcons CSS but does not set up the PrimeVue plugin or theme preset.
- `Navbar.vue` already uses some PrimeVue components (`Button`, `Menu`) directly but without global PrimeVue app setup.

### Global Setup (PrimeVue)
1) Add PrimeVue plugin and theme in `src/main.ts`.

```ts
// src/main.ts (example)
import PrimeVue from 'primevue/config';
import Aura from '@primevue/themes/aura'; // or Lara/Nora per preference

const app = createApp(App);
app.use(PrimeVue, { theme: { preset: Aura }, ripple: true });
```

2) Ensure global CSS order (already present):
   - `primeicons/primeicons.css`
   - `primeflex/primeflex.css`
   - App styles `assets/css/main.scss`

3) Optionally register commonly used components globally to reduce repetitive imports (optional; local imports are fine):

```ts
// after app.use(PrimeVue, ...)
// app.component('DataTable', DataTable);
// app.component('Column', Column);
// app.component('Button', Button);
// app.component('InputText', InputText);
// app.component('Sidebar', Sidebar);
```

Theme notes: Aura or Lara are both modern and neutral. Aura pairs well with the screenshots’ flat styling. See theming options in [PrimeVue Theming](https://primevue.org/theming).

### Component Mapping (Screenshots → PrimeVue)
- Top App Header: `Menubar` or custom flex with `Avatar`, `Menu` for profile dropdown, `Button` for auth actions.
- Secondary App Header tabs “My Library / My Collections”: `TabMenu` or two `Button`s styled as tabs; alternatively `Menubar` model.
- Search input: `InputText` with left icon (`pi pi-search`), full width on toolbar.
- Expand/Collapse All: `Button` pair in the toolbar.
- Upload PDF: `FileUpload` (mode=basic) or `Button` triggering custom upload flow.
- Library table: `DataTable` with columns: expander, Title, Last updated, Source, Checkbox. Use `rowExpansion` for Summary/Key Points section.
- Checkbox column: `Column` with `Checkbox` component bound to selection array.
- Source link: anchor styled via table body template.
- Filter panel (left):
  - Panel container: `Sidebar` or a fixed `Panel` column.
  - Filter groups with nested items and checkboxes: `Tree` with `selectionMode="checkbox"` or `Accordion` + `Checkbox` lists.
  - Selected filters footer and Clear: `Chips` or small `Tag`s and a `Button`.

Useful references: [DataTable](https://primevue.org/datatable), [Row Expansion](https://primevue.org/datatable/rowexpansion/), [Tree](https://primevue.org/tree), [Sidebar](https://primevue.org/sidebar), [Menubar](https://primevue.org/menubar), [FileUpload](https://primevue.org/fileupload).

### Pages and Components

1) Views
- `views/DocumentContainer.vue` (Library):
  - Wrap in `Grid`/PrimeFlex for optional left filter column.
  - Top toolbar with search, expand/collapse, Upload PDF.
  - `DataTable` for documents with expansion template for Summary/Key Points.
  - Optional prop or route query toggles whether the filter panel is visible.

- `views/library/Collections.vue` (Collections):
  - Use `DataView` or `DataTable` per existing needs; ensure header aligns with Library styles.

2) Library child components
- `components/library/LibraryToolbar.vue`
  - Contains search `InputText`, expand/collapse `Button`s, and `FileUpload`/`Button`.
  - Emits `search`, `expandAll`, `collapseAll`, `upload` events.

- `components/library/LibraryTable.vue`
  - `DataTable` with:
    - `:value="documents"`, `rowExpansionTemplate` for Summary / Key Points panel.
    - `selectionMode="multiple"` via checkbox column and `v-model:selection`.
    - Columns: expander, title (with link), updatedAt, source (anchor), checkbox.

- `components/library/LibraryFilters.vue`
  - Left panel using `Tree` with `selectionMode="checkbox"` representing topics/tags.
  - Emits `update:filters` with selected keys; shows selected filter badges and Clear button.

3) Header/Nav
- Replace ad-hoc header layout with `Menubar` + profile `Avatar` and `Menu` (dropdown) in `components/Navbar.vue` while preserving current auth store logic.
- Middle section “My Library / My Collections” can be a `TabMenu` bound to router.

### Data Model and State (Pinia)
- `stores/library_store.ts` (new):
  - State: `documents`, `loading`, `selectedDocumentIds`, `expandedRows`, `filters`, `searchText`.
  - Actions: `fetchDocuments()`, `applyFilters()`, `clearFilters()`, `toggleExpandAll()`.
  - Getters: `filteredDocuments` computed from `documents`, `filters`, and `searchText`.

### Step-by-Step Implementation
1) PrimeVue setup
   - Add PrimeVue plugin + theme in `src/main.ts` (see snippet above).
   - Verify icons and flex utilities load correctly.

2) Header
   - Refactor `components/Navbar.vue` to a `Menubar` model with right-end profile `Avatar` and `Menu` dropdown for Sign Out/Login.
   - Add two center tabs “My Library” and “My Collections” using `TabMenu` or `Button` group wired to router.

3) Library view
   - Create `components/library/LibraryToolbar.vue` with search input, expand/collapse buttons, and upload button.
   - Create `components/library/LibraryTable.vue` implementing a `DataTable` with row expansion templates showing Summary + Key Points.
   - Wire expand/collapse all via `expandedRows` map and toolbar events.
   - Create `components/library/LibraryFilters.vue` using `Tree` with checkbox selection; show selected chips and Clear button.
   - Update `views/DocumentContainer.vue` to compose `LibraryToolbar`, optional `LibraryFilters` (left column), and `LibraryTable` (right column) matching both screenshots.

4) Store
   - Add `stores/library_store.ts` with actions/getters above; integrate with toolbar search and filter emissions.

5) Styles & Theme
   - Use PrimeFlex for layout (`grid`, `col-fixed`, `col`); apply small border radius and `surface-*` classes to match screenshot cards.
   - Keep typography via Roboto (already present) and adjust CSS tokens if needed.

6) Upload PDF
   - For simple flow, use `FileUpload` (mode=basic) and emit the selected file to an existing API client; or keep a `Button` to open a custom dialog.

7) Accessibility
   - Ensure buttons have labels or `aria-label`s.
   - Table rows and expansion templates follow semantic structure per PrimeVue examples.

### Key PrimeVue Snippets

Row expansion in table:
```vue
<DataTable :value="documents" v-model:expandedRows="expandedRows" dataKey="id">
  <Column expander style="width:3rem" />
  <Column field="title" header="Title" />
  <Column field="updatedAt" header="Last updated" />
  <Column header="Source">
    <template #body="{ data }">
      <a :href="data.sourceUrl" target="_blank" rel="noopener noreferrer">{{ data.sourceHost }}</a>
    </template>
  </Column>
  <Column selectionMode="multiple" style="width:3rem" />

  <template #expansion="{ data }">
    <div class="p-3">
      <div class="text-sm text-600 mb-2">Summary</div>
      <div class="mb-3">{{ data.summary }}</div>
      <div class="text-sm text-600 mb-2">Key Points</div>
      <ul class="pl-3">
        <li v-for="(kp, i) in data.keyPoints" :key="i">{{ kp }}</li>
      </ul>
    </div>
  </template>
</DataTable>
```

Filter tree with checkbox selection:
```vue
<Tree :value="nodes"
      selectionMode="checkbox"
      v-model:selectionKeys="selectedKeys"
      class="w-full"
/>
```

Toolbar with search and actions:
```vue
<div class="flex align-items-center justify-content-between gap-2">
  <span class="p-input-icon-left flex-1">
    <i class="pi pi-search" />
    <InputText v-model="searchText" placeholder="Search" class="w-full" />
  </span>
  <div class="flex gap-2">
    <Button label="Expand All" icon="pi pi-plus" @click="$emit('expandAll')" />
    <Button label="Collapse All" icon="pi pi-minus" @click="$emit('collapseAll')" />
    <FileUpload mode="basic" name="file" chooseLabel="Upload PDF" @select="$emit('upload', $event.files)" />
  </div>
  </div>
```

### Routing and Guards
- Keep `router/index.ts` as-is; `Navbar` controls visual state between website header and app header. When refactoring to `Menubar` + tabs, preserve current afterEach class toggles or replace with computed visibility bound to route name.

### Deliverables Checklist
- PrimeVue plugin + theme configured in `src/main.ts` with ripple enabled.
- Refactored `Navbar.vue` using `Menubar`/`TabMenu`, `Avatar`, and `Menu` for profile.
- New components: `LibraryToolbar.vue`, `LibraryTable.vue`, `LibraryFilters.vue` under `components/library/`.
- Updated `DocumentContainer.vue` to compose the toolbar, filters panel, and table with responsive PrimeFlex grid.
- New Pinia store `stores/library_store.ts` for documents, filters, search, selection, and expansion.
- Upload PDF action stub or integrated API call.
- Styling aligned to screenshots using Aura/Lara theme tokens and PrimeFlex utilities.

### QA Checklist
- Expand/collapse all affects only currently visible filtered rows.
- Search filters client-side by title and summary; server-side search can be swapped in later.
- Filter selections persist when toggling the filter panel.
- Keyboard navigation and focus rings visible on toolbar controls and table rows.
- Responsive layout: filter panel collapses on small screens (use `Sidebar` or hide to second screenshot state).

---
References: PrimeVue site and docs [primevue.org](https://primevue.org/)



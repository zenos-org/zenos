// Paper-like page (A4) with margins; the area around the page shows as grey.
// renderConfig.background forces the page (paper) to stay white even in dark mode.
export const ZENOS_DOC_STYLE = {
  documentFlavor: 1, // DocumentFlavor.TRADITIONAL (paginated)
  pageSize: { width: 794, height: 1123 },
  marginTop: 96,
  marginBottom: 96,
  marginLeft: 96,
  marginRight: 96,
  renderConfig: {
    background: { rgb: '#ffffff' },
  },
}

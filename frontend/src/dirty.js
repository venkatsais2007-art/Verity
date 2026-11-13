let dirty = false;
export const setDirty = (v) => { dirty = !!v; };
export const isDirty = () => dirty;
export const confirmLeave = () =>
  !dirty || window.confirm("You have unsaved changes. Leave this page and lose them?");

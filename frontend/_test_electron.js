
const { app } = require('electron');
app.whenReady().then(() => {
  console.log('Electron started OK');
  console.log('isPackaged:', app.isPackaged);
  console.log('resourcesPath:', process.resourcesPath);
  setTimeout(() => app.quit(), 3000);
});

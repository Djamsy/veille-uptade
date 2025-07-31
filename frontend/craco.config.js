const path = require('path');

// Optionnel : désactiver le hot reload via variable d’environnement
const disableHotReload = process.env.DISABLE_HOT_RELOAD === 'true';

module.exports = {
  webpack: {
    configure: (webpackConfig) => {
      // 🔧 Bloque tout usage de eval (important pour Render)
      webpackConfig.devtool = false;

      // ❌ Supprime HotModuleReplacementPlugin si hot reload désactivé
      if (disableHotReload) {
        webpackConfig.plugins = webpackConfig.plugins.filter(
          plugin => plugin.constructor.name !== 'HotModuleReplacementPlugin'
        );
      }

      return webpackConfig;
    },
  },
  devServer: (devServerConfig) => {
    // Optionnel : Empêche le hot reload en local aussi
    if (disableHotReload) {
      devServerConfig.hot = false;
      devServerConfig.liveReload = false;
      devServerConfig.watchFiles = [];
    }

    return devServerConfig;
  }
};

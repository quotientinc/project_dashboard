import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

const customTheme = {
  dark: false,
  colors: {
    background: '#FAFAFA',
    surface: '#FFFFFF',
    primary: '#1976D2',
    secondary: '#424242',
    accent: '#FF4081',
    success: '#4CAF50',
    warning: '#FB8C00',
    error: '#FF5252',
    info: '#2196F3',
    'on-background': '#212121',
    'on-surface': '#212121',
  },
}

export default createVuetify({
  components,
  directives,
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: { mdi },
  },
  theme: {
    defaultTheme: 'customTheme',
    themes: {
      customTheme,
    },
  },
  defaults: {
    VCard: {
      elevation: 1,
    },
    VBtn: {
      variant: 'flat',
    },
    VTextField: {
      variant: 'outlined',
      density: 'comfortable',
    },
    VSelect: {
      variant: 'outlined',
      density: 'comfortable',
    },
  },
})

# NoSteam2Steam

NoSteam2Steam es una herramienta diseñada para gestionar juegos no pertenecientes a Steam, permitiendo sincronizar partidas guardadas, agregar juegos a la biblioteca de Steam y realizar respaldos automáticos. Este proyecto está optimizado para su uso en Steam Deck, pero también puede ser utilizado en otras plataformas si se realizan modificaciones (especialmente en las conversiones de rutas que dependen de cada SO).

Este proyecto se apoya en Game Backup Monitor (GBM) como referencia/herramienta principal de creacción de backups en windows. Con ciertos ajustes se podría hacer una herramienta independiente, no obstante está fuera del alcance inicial previsto para el proyecto. 

El proyecto presupone backups en el mismo formato que GBM y una herramienta de sincronización de carpetas. NoSteam2Steam usa esta carpeta para sincronizar las partidas entre los datos de guardado locales y las partidas de windows. En nuestro caso para la sincronización de carpetas entre windows y steamdeck hemos elegido syncthing, pero se puede usar cualquier otra herramienta que cumpla la misma función.

## Características

* **Sincronización de partidas guardadas:** Sincroniza automáticamente las partidas guardadas entre diferentes dispositivos.
* **Gestión de juegos no pertenecientes a Steam:** Agrega juegos de otras plataformas (como GOG, Heroic, etc.) a la biblioteca de Steam.
* **Respaldo de partidas guardadas:** Crea respaldos automáticos de las partidas guardadas en formato \`.7z\`.
* **Restauración de partidas perdidas:** Detecta y restaura partidas guardadas que puedan haberse perdido.


### Dependencias:

* Python 3.11 o superior
* \`py7zr\` para la manipulación de archivos \`.7z\`
* \`zenity\` para la interfaz gráfica de usuario
* \`requests\` para consultas a APIs externas
* \`vdf\` para manejar archivos de configuración de Steam

### Sistema operativo:

* Steam Deck (Linux)
* Otras distribuciones de Linux (no probado/puede necesitar ajustes menores)

## Instalación

### Clonar el repositorio:

```bash
git clone https://github.com/JesusSolisOrtega/NoSteam2Steam.git
cd NoSteam2Steam
```

### Instalar dependencias:

```bash
pip install -r requirements.txt
```

## Uso

### Menú principal

Ejecuta el script principal para acceder al menú de opciones:

```bash
python noSteam2Steam.py
```

Las opciones disponibles incluyen:

  * **Sincronización automática:** Agrega juegos y sincroniza partidas guardadas.
  * **Agregar juegos a Steam automáticamente:** Detecta y agrega juegos no pertenecientes a Steam.
  * **Sincronización de partidas guardadas:** Sincroniza manualmente las partidas guardadas.
  * **Agregar manualmente un juego a Steam:** Permite agregar juegos específicos.
  * **Limpiar configuración de NoSteam2Steam:** Elimina configuraciones y datos temporales.
  * **Activar/desactivar Syncthing:** Gestiona el servicio de sincronización en segundo plano.
  * **Cambiar carpetas de juegos sincronizados:** Modifica las carpetas donde se buscan juegos y partidas guardadas.
  * **Salir:** Cierra la aplicación.


### Funcionamiento (Breve explicación técnica)

El programa se compone de 3 (realmente 4) módulos principales, cada uno realiza una función específica. 

El primero es la identificación de juegos, para lo cual busca en la carpeta de sincronización designada y busca los ejecutables de los juegos. Luego adicionalmente complementa con información de lutris que usará despues. 

El segundo se encarga de agregar correctamente el juego a steam, asociar las imagenes, etc. Un aspecto importante de esta fase es que calcula los ids de los juegos agregados lo cual es necesario para la fase de sincronización. 

El tercero (el motivo principal para la creación del programa), es el encargado de la sincronización de las partidas. Este módulo lee los backups de la carpeta designada y los sincroniza con los archivos locales de las partidas de juegos agregados a steam. Para ello nos apoyamos en la estructura de los backups creados por Game Backup Monitor (GBM) y en los archivos de configuraciones de juegos de GBM y ludusavi.

*El último módulo es la busqueda manual de los juegos que a nivel funcional cumple la misma función que el primer módulo para la identificación, pero permite la selección por parte del usuario y sobreescribe la entrada en caso de haber sido detectado previamente un juego asociado a dicho ejecutable. La detección automática está programada para respetar las selecciones manuales.

*Por último hay una serie de funcionalidades extra como la eliminación de configuraciones en caso de que haya un comportamiento indebido o simplemente para hacer un añadido y/o sincronización limpios. El programa está pensado para tener el mejor balance entre fiabilidad (por ejemplo, no sobreescribir partidas en caso de duda como que haya varios backups del mismo juego) y minimizar las preguntas al usuario cuando sea posible para agilizar y simplificar la ejecución. Por ello cuando se selecciona sincronizar un archivo o hay alguna entrada manual, asume que para futuras ejecuciones este será el comportamiento deseado.

*Tanto el primer como el segundo módulo actualizan los datos en caso de que haya cambios (Salvo la descarga de imágenes que no se vuelven a descargar en caso de existir, ya que asumimos que las imágenes no necesitan actualizarse una vez encontradas)

La mayoría de las opciones del diálogo son autoexplicativas:

1.- Sincronización automática -> El programa completo, es decir identifica, agrega y sincroniza las partidas de los juegos agregados.

2.- Agregar juegos a Steam automáticamente -> ejecuta el primer y segundo módulo (idetifica y agrega a steam)

3.- Sincronización de partidas guardadas -> ejecuta la sincronización de partidas

4.- Limpiar configuración -> Distintas opciones para eliminar la configuración/decisiones respecto a los juegos agregados, las partidas sincronizadas o ambas.

5.- Activar/desactivar Syncthing -> permite activar el servicio de syncthing para que funcione en el modo juego de steam (para la sincronización de las carpetas, ya sea de las partidas guardadas o si se ha decidido sincronizar una carpeta con las instalaciones de los juegos, etc.**)

6.- Cambiar carpetas de juegos sincronizados -> Permite seleccionar las carpetas en las que se encontrarán los juegos sincronizados, se recomienda usar la carpeta por defecto ($Home/games), aunque se pueden agregar varias o borrarlas.


** Por pruebas realizadas, syncthing funciona bien para los respaldos de partidas guardadas, pero con los juegos ha dado problemas para archivos grandes, con lo que se recomienda otros métodos o programas para pasar los juegos al dispositivo desde windows (o hacerlo manualmente)

## Agradecimientos y referencias

Las dos principales referencias en que se ha basado el proyecto y cuyos archivos de configuraciones usamos como base de la búsqueda/identificación de juegos y archivos de guardado:

GBM -> https://mikemaximus.github.io/gbm-web/

Ludusavi Manifest -> https://github.com/mtkennerly/ludusavi-manifest

Debo mencionar los siguientes repositorios que he usado de referencia para conseguir averiguar cómo modificar correctamente el binario de accesos directos de steam (shortcuts.vdf) y el cálculo de los distintos ids que steam usa para cada juego en sus operaciones internas:

Steam Shortcut Manager -> https://github.com/CorporalQuesadilla/Steam-Shortcut-Manager

Heroic Games Launcher -> https://github.com/Heroic-Games-Launcher/HeroicGamesLauncher/tree/main

SteamGridDB -> https://github.com/SteamGridDB/steam-rom-manager/blob/master/src/lib/helpers/steam/generate-app-id.ts


## Contribuciones

¡Las contribuciones son bienvenidas\! Si deseas colaborar, por favor:

1.  Haz un fork del repositorio.
2.  Crea una rama para tu funcionalidad o corrección de errores
3.  Realiza tus cambios y haz un commit
4.  Envía un pull request.

## Licencia

Copyright (c) 2025 Jesús Solís Ortega

Este software se distribuye para fines educativos y personales.  
Queda prohibido cualquier uso comercial, distribución, sublicencia, venta o integración en productos o servicios con fines lucrativos, excepto por el titular de los derechos.  
Se permite el uso, copia y modificación para fines no comerciales, siempre que se mantenga este aviso de copyright.

Para cualquier uso comercial, contactar con el autor.

NO SE OTORGA NINGUNA GARANTÍA, EXPLÍCITA O IMPLÍCITA.

## Contacto

Si tienes preguntas o sugerencias, no dudes en abrir un issue en el repositorio o contactarme directamente.
Si tienes algún proyecto comercial donde quieras integrarlo contactame y seguramente no haya mucho problema ¡Gracias por usar NoSteam2Steam\!

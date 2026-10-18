
utilizando la libreria de python streamlit desarrolla la siguiente plataforma.

- La plataforma debe tener foros de discucion donde los estudiantes puedan crear una publicacion con alguna problematica, duda o tema en particular que quieran discutir,
en esa publicacion debe de existir la habilitacion de un apartado donde los demas usuarios puedad contestar o realizar comentarios acerca de la tematica.
- el perfil de cada persona debe de poder tener opciones personalizables como lo son el nombre, alias, correo, contrasena e imagen de perfil (agrega otros datos que consideres relevantes)
- debe existir una vista en donde los estudiantes puedan colocar el plan de estudios, en que semestre van, que materias estan cursando y asi mismo que materias ya han cursado, guardando su historia academica.
- cada materia tiene que tener la opcion de poder agregarle items correspondientes a un nombre, descripcion y calificacion correspondiente del trabajo o tarea desarrollada en esa materia.
- con esa informacion se debe de porder calcular el promedio del estudiante, teniendo en cuenta las materias vistas en el semestre y su calificacion obtenida.
- de igual forma se debe de calcular el promedio general teniendo encuenta las notas de las materias vistas hasta el momento.
- debe existir un apartado de retos dinamicos, en donde hay retos generales para cada uno de los estudiantes y que es lo mismo para los antiguos y nuevos usuarios, pero tambien existe la opcion de que cada estudiante cree un reto, en donde otros estudiantes pueden suscribirse para intentar completarlo.
- estos retos deben evaluar cuantas personas participaron, quien lo cumplio primero, etc. mostrando en un baner a la derecha ese ranking
- debe tener opciones de seguir y tener seguidores, para de esta forma poder realizar los retos interactivos.
- debe tener opciones para enviar mensajes de apoyo a otro usuario como un: vamos tu puedes, no te rindas, etc.
- debes de crear un panel de administrador donde se puedan ver todos los elmentos creados y la informacion de un usuario asi como metricas generales para evaluar situacion de un estudiante en particular o un grupo de ellos

Estas son algunas caracteristicas generales para que entiendas el proposito de aplicacion, si vez que podemos agregar algo mas, detallalo en un archivo .md donde explique como funciona el proyecto, que hiciste y que agregaste.

es importante que si necesitas utilizar una db uses postgrsql, mysql o mariadb segun consideres, utilizalo por medio de docker.
para la autenticacion, realiza un login basico, puedes utilizar keyclock para ello.

ya el ambiente virtual esta creado, instala las dependencias ahi, asi mismo crea un makefile para poder crear, subir y bajar el proyecto.
crea el archivo .gitignore y agrega los archivos que no sean necesarios ahi, para que no suban al repo.
crea el archivo pre-commit y sus archivos necesarios para utilizar las librerias de isort y ruff para el estandar y calidad del codigo.

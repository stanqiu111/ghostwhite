[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/etkNZkSE)
CMPUT404-project-socialdistribution
===================================

CMPUT404-project-socialdistribution

See [the web page](https://uofa-cmput404.github.io/general/project.html) for a description of the project.

Make a distributed social network!

## License

* This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.

## Copyright

The authors claiming copyright, if they wish to be known, can list their names here...

| Name          | GitHub Username |
| ------------- | --------------- | 
| Jueun (Krystal) Kim     | rlawndms        |
| Evelyn Nguyen | LinhNguyen310   |
| Stan Qiu      | stanqiu111      |
| Ximeng Duan   | XimengDuan      |
| Michael Yang  | MichaelY223     |
| Shuran Kong   | arinnaaa        |

## Nodes

| Name          | Node            | Username        | Password       |
| ------------- | --------------- | --------------- |--------------- |
| Jueun (Krystal) Kim | [https://krystal-7a3d144806fa.herokuapp.com/](https://krystal-7a3d144806fa.herokuapp.com/home/) | krystal | krystal |
| Evelyn Nguyen | https://ghostwhite-evelyn-node-f268ea95378e.herokuapp.com/ | linhn | linhnprod |
| Stan Qiu      | https://stan-2dd8cc96fa3e.herokuapp.com/ | stan_node | stan1234 |
| Ximeng Duan   | https://ghostwhite-ximeng-c739441113d7.herokuapp.com/ | ximeng | dxm021108 |
| Michael Yang  | https://ghostwhite-michael-30ba71539df9.herokuapp.com/ | MichaelYang | MichaelPassword@123 |
| Shuran Kong   | https://cmput404-app-shuran-d178a18f2c5f.herokuapp.com/ | shuran | shurantest123! |

## To run tests, node-to-node communication
      python manage.py test nodes.tests

## run inbox tests
      python manage.py test inbox

## API Documentation

You can view the automatically generated API documentation using **drf-spectacular (Swagger UI)**.

1. Make sure you're in the virtual environment

   ```bash
   source venv/bin/activate
   
2. Install dependencies

   ```bash
   pip install drf-spectacular
   
4. Run the Django development server
   
   ```bash
   python manage.py runserver

5. Once the server is running, open the following URL in your browser:  http://127.0.0.1:8000/api/docs/
6. For more details with User Stories, check: https://github.com/uofa-cmput404/f25-project-ghostwhite/blob/08726d1c9b2116d46836f2dc93f358dd36146afb/api_doc.md

## Related Documentations

User Stories: https://docs.google.com/spreadsheets/d/1pNFONRS94QShi56lbZggabKdFVjzGXbFjxKpgwdsrWY/edit?gid=0#gid=0

Figma: https://www.figma.com/design/eOnTTGBQ0kVjNBlamF3RqB/CMPUT404_Project?node-id=0-1&t=z3hQl4rjija8zXbG-1

DataBase Design: https://docs.google.com/document/d/1N5pYmGQqjjYz-mZyWd0076LR-xhAuy6zakLM-ltd8Ug/edit?tab=t.0

External node connection design: https://docs.google.com/document/d/1pWfzVwklOOw3OyrlPQfki7emm3yVROubkzIoKSGH8KE/

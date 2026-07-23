# def bind(source, property_name, setter, transform=lambda x: x):
#     meta = source.metaObject()

#     property_index = meta.indexOfProperty(property_name)
#     prop = meta.property(property_index)

#     def update():
#         setter(
#             transform(prop.read(source))
#         )

#     notify = prop.notifySignal()
#     notify_name = bytes(notify.name()).decode()

#     getattr(source, notify_name).connect(update)

#     update()

# def bind(source, properties, setter, getter):
#     if isinstance(properties, str):
#         properties = (properties,)

#     def update():
#         setter(getter(source))

#     meta = source.metaObject()

#     for name in properties:
#         prop = meta.property(meta.indexOfProperty(name))
#         notify_name = bytes(prop.notifySignal().name()).decode()

#         getattr(source, notify_name).connect(update)

#     update()

from typing import Callable, Any


def bind(
    signal,
    setter: Callable[[Any], None],
    getter: Callable[[], Any],
) -> None:
    def update(*_):
        setter(getter())

    signal.connect(update)
    update()